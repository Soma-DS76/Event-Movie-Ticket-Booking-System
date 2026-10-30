import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.booking import Booking, BookingSeat, ConfirmedSeat, Payment
from app.models.event import Event, Show
from app.models.refund import Refund
from app.models.user import User
from app.models.venue import Screen, Seat
from app.redis_client import redis_client
from app.schemas.payment import PaymentCreate, PaymentResponse
from app.services.email_service import send_booking_confirmation, send_payment_failed
from app.services.email_service import send_booking_cancelled
from app.services.notifications import notify_waitlisted_customers
from app.services.ticket_service import generate_booking_ticket
from app.websocket_manager import manager


logger = logging.getLogger(__name__)
router = APIRouter(tags=['Payments'])


def get_seat_lock_owner(key: str):
    try:
        value = redis_client.get(key)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail='Seat-lock service is temporarily unavailable',
        ) from exc
    return value.decode('utf-8') if isinstance(value, bytes) else value


def release_customer_seat_locks(show_id: int, seat_ids: list[int], customer_id: int):
    script = "\n    if redis.call('GET', KEYS[1]) == ARGV[1] then\n        return redis.call('DEL', KEYS[1])\n    end\n    return 0\n    "
    for seat_id in seat_ids:
        key = f"lock:show:{show_id}:seat:{seat_id}"
        try:
            redis_client.eval(script, 1, key, str(customer_id))
        except Exception:
            logger.exception(
                'Could not release seat lock for show %s, seat %s', show_id, seat_id
            )


def _refund_late_payment(db: Session, booking: Booking, payment: Payment, now: datetime):
    payment.status = 'Refunded'
    payment.paid_at = now
    booking.status = 'Cancelled'
    db.add(
        Refund(
            booking_id=booking.id,
            payment_id=payment.id,
            amount=payment.amount,
            reason='Late Payment',
            status='Refunded',
        )
    )


@router.post(
    '/bookings/{booking_id}/pay',
    response_model=PaymentResponse,
    status_code=201,
)
def pay_for_booking(
    booking_id: int,
    payload: PaymentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles('Customer')),
):
    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id, Booking.customer_id == user.id)
        .with_for_update()
        .first()
    )
    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')
    if booking.status not in ('Pending', 'Pending Payment'):
        raise HTTPException(
            status_code=409, detail='Only pending bookings can be paid'
        )

    now = datetime.now()
    is_expired = booking.expires_at is not None and now >= booking.expires_at
    if is_expired and payload.simulate_status == 'Failed':
        booking.status = 'Expired'
        db.commit()
        raise HTTPException(status_code=409, detail='This booking has expired')

    booking_seats = (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .order_by(BookingSeat.seat_id)
        .all()
    )
    if not booking_seats:
        raise HTTPException(status_code=400, detail='Booking has no seats')

    amount = booking.grand_total
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail='Booking has an invalid payment amount')

    payment = Payment(
        booking_id=booking.id,
        payment_reference=f"TXN-{now:%Y%m%d}-{uuid4().hex[:6].upper()}",
        amount=amount,
        payment_method=payload.payment_method,
        status=payload.simulate_status,
        paid_at=now if payload.simulate_status == 'Success' else None,
    )
    db.add(payment)
    db.flush()

    if payload.simulate_status == 'Failed':
        db.commit()
        db.refresh(payment)
        background_tasks.add_task(
            send_payment_failed, user.email, booking.booking_reference
        )
        return payment

    show = db.query(Show).filter(Show.id == booking.show_id).first()
    seats = (
        db.query(Seat)
        .join(BookingSeat, BookingSeat.seat_id == Seat.id)
        .filter(
            BookingSeat.booking_id == booking.id,
            Seat.is_active.is_(True),
            Seat.screen_id == show.screen_id if show is not None else False,
        )
        .all()
    )
    seat_ids = [item.seat_id for item in booking_seats]
    locks_valid = (
        show is not None
        and show.status == 'Scheduled'
        and len(seats) == len(seat_ids)
        and all(
            get_seat_lock_owner(f"lock:show:{booking.show_id}:seat:{seat_id}")
            == str(user.id)
            for seat_id in seat_ids
        )
    )
    if is_expired:
        locks_valid = False

    if locks_valid:
        try:
            with db.begin_nested():
                db.add_all(
                    ConfirmedSeat(
                        booking_id=booking.id,
                        show_id=booking.show_id,
                        seat_id=seat_id,
                    )
                    for seat_id in seat_ids
                )
                db.flush()
        except IntegrityError:
            locks_valid = False

    if not locks_valid:
        _refund_late_payment(db, booking, payment, now)
        db.commit()
        db.refresh(payment)
        release_customer_seat_locks(booking.show_id, seat_ids, user.id)
        for seat_id in seat_ids:
            manager.broadcast_sync(
                booking.show_id,
                {'type': 'seat_update', 'seat_id': seat_id, 'status': 'Available'},
            )
        background_tasks.add_task(
            send_booking_cancelled,
            user.email,
            booking.booking_reference,
            str(payment.amount),
        )
        notify_waitlisted_customers(
            db, booking.show_id, seat_ids, background_tasks
        )
        return payment

    booking.status = 'Confirmed'
    booking.confirmed_at = now
    try:
        ticket_path = generate_booking_ticket(db, booking, payment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(payment)
    event = db.query(Event).filter(Event.id == show.event_id).first()
    background_tasks.add_task(
        send_booking_confirmation,
        user.email,
        user.full_name,
        booking.booking_reference,
        event.title if event is not None else 'Event',
        str(payment.amount),
        ticket_path,
    )
    release_customer_seat_locks(booking.show_id, seat_ids, user.id)
    for seat_id in seat_ids:
        manager.broadcast_sync(
            booking.show_id,
            {'type': 'seat_update', 'seat_id': seat_id, 'status': 'Booked'},
        )
    return payment


@router.get(
    '/bookings/{booking_id}/payments',
    response_model=list[PaymentResponse],
)
def list_booking_payments(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles('Customer', 'Organizer', 'Admin')),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')

    if user.role == 'Customer' and booking.customer_id != user.id:
        raise HTTPException(status_code=403, detail='Access denied')
    if user.role == 'Organizer':
        show = db.query(Show).filter(Show.id == booking.show_id).first()
        event = db.query(Event).filter(Event.id == show.event_id).first() if show else None
        if event is None or event.organizer_id != user.id:
            raise HTTPException(status_code=403, detail='Access denied')

    return (
        db.query(Payment)
        .filter(Payment.booking_id == booking.id)
        .order_by(Payment.created_at, Payment.id)
        .all()
    )
