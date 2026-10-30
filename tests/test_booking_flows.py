from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.booking import Booking, BookingSeat, ConfirmedSeat
from app.models.event import Event, SeatCategoryPrice, Show
from app.models.refund import Refund
from app.models.user import User
from app.models.venue import Screen, Seat, Venue
from app.routers import payments
from app.routers.seat_locking import validate_no_single_empty_seat
from app.schemas.payment import PaymentCreate
from app.services.billing_service import calculate_booking_bill
from app.services.refund_service import calculate_customer_refund


@pytest.fixture
def db():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_booking_fixture(db):
    customer = User(
        full_name='Test Customer',
        email='customer@example.test',
        phone='1234567890',
        hashed_password='hashed',
        role='Customer',
        is_active=True,
        is_approved=True,
    )
    venue = Venue(name='Test Venue', city='Test City', address='Test Address')
    db.add_all([customer, venue])
    db.flush()
    screen = Screen(venue_id=venue.id, name='Screen 1', total_seats=1)
    db.add(screen)
    db.flush()
    seat = Seat(
        screen_id=screen.id,
        row_label='A',
        seat_number=1,
        category='Silver',
        is_active=True,
    )
    event = Event(
        organizer_id=customer.id,
        title='Test Event',
        category='Movie',
        language='English',
        description='',
        duration_minutes=120,
        age_rating='U',
        status='Published',
    )
    db.add_all([seat, event])
    db.flush()
    start = datetime.now() + timedelta(hours=2)
    show = Show(
        event_id=event.id,
        screen_id=screen.id,
        show_date=date.today(),
        start_time=start,
        end_time=start + timedelta(hours=2),
        booking_closes_at=start - timedelta(minutes=30),
        status='Scheduled',
    )
    db.add(show)
    db.flush()
    db.add(SeatCategoryPrice(show_id=show.id, category='Silver', price=Decimal('100')))
    booking = Booking(
        booking_reference='BK-TEST-1',
        customer_id=customer.id,
        show_id=show.id,
        total_amount=Decimal('153.40'),
        ticket_total=Decimal('100'),
        convenience_fee=Decimal('30'),
        gst_amount=Decimal('23.40'),
        grand_total=Decimal('153.40'),
        seat_count=1,
        status='Pending Payment',
        expires_at=datetime.now() + timedelta(minutes=10),
    )
    db.add(booking)
    db.flush()
    db.add(
        BookingSeat(
            booking_id=booking.id,
            show_id=show.id,
            seat_id=seat.id,
            price=Decimal('100'),
        )
    )
    db.commit()
    return customer, booking, seat


def test_failed_payment_can_be_retried_and_success_confirms_booking(db, monkeypatch):
    customer, booking, seat = create_booking_fixture(db)
    monkeypatch.setattr(payments, 'get_seat_lock_owner', lambda key: str(customer.id))
    monkeypatch.setattr(payments, 'release_customer_seat_locks', lambda *args: None)
    monkeypatch.setattr(payments, 'generate_booking_ticket', lambda *args: 'ticket.pdf')
    monkeypatch.setattr(payments.manager, 'broadcast_sync', lambda *args: None)

    failed = payments.pay_for_booking(
        booking.id,
        PaymentCreate(payment_method='UPI', simulate_status='Failed'),
        BackgroundTasks(),
        db,
        customer,
    )
    assert failed.status == 'Failed'
    assert db.get(Booking, booking.id).status == 'Pending Payment'

    successful = payments.pay_for_booking(
        booking.id,
        PaymentCreate(payment_method='Card', simulate_status='Success'),
        BackgroundTasks(),
        db,
        customer,
    )
    assert successful.status == 'Success'
    assert successful.amount == Decimal('153.40')
    assert db.get(Booking, booking.id).status == 'Confirmed'
    assert (
        db.query(ConfirmedSeat)
        .filter_by(show_id=booking.show_id, seat_id=seat.id)
        .count()
        == 1
    )

    with pytest.raises(HTTPException) as exc_info:
        payments.pay_for_booking(
            booking.id,
            PaymentCreate(payment_method='UPI', simulate_status='Success'),
            BackgroundTasks(),
            db,
            customer,
        )
    assert exc_info.value.status_code == 409


def test_late_success_is_refunded_when_redis_lock_expired(db, monkeypatch):
    customer, booking, _ = create_booking_fixture(db)
    booking.expires_at = datetime.now() - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(payments, 'release_customer_seat_locks', lambda *args: None)
    monkeypatch.setattr(payments.manager, 'broadcast_sync', lambda *args: None)

    payment = payments.pay_for_booking(
        booking.id,
        PaymentCreate(payment_method='UPI', simulate_status='Success'),
        BackgroundTasks(),
        db,
        customer,
    )
    assert payment.status == 'Refunded'
    assert db.get(Booking, booking.id).status == 'Cancelled'
    refund = db.query(Refund).filter_by(booking_id=booking.id).one()
    assert refund.reason == 'Late Payment'


def test_single_empty_seat_rule():
    seats = [
        SimpleNamespace(id=index, seat_number=index, row_label='A', is_active=True)
        for index in range(1, 5)
    ]
    with pytest.raises(HTTPException) as exc_info:
        validate_no_single_empty_seat(seats, {1, 3})
    assert exc_info.value.status_code == 409

    validate_no_single_empty_seat(seats, {1, 4})


def test_bill_and_customer_cancellation_policy():
    bill = calculate_booking_bill([Decimal('100'), Decimal('150')])
    assert bill['ticket_total'] == Decimal('250.00')
    assert bill['convenience_fee'] == Decimal('60.00')
    assert bill['gst_amount'] == Decimal('55.80')
    assert bill['grand_total'] == Decimal('365.80')

    assert calculate_customer_refund(
        Decimal('100'), datetime.now() + timedelta(hours=25)
    ) == Decimal('100.00')
    assert calculate_customer_refund(
        Decimal('100'), datetime.now() + timedelta(hours=12)
    ) == Decimal('50.00')
    with pytest.raises(ValueError):
        calculate_customer_refund(
            Decimal('100'), datetime.now() + timedelta(hours=1)
        )
