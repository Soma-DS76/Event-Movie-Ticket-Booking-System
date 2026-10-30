
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.event import Event, Show, SeatCategoryPrice
from app.models.venue import Seat
from app.models.booking import Booking, BookingSeat, ConfirmedSeat
from app.redis_client import redis_client
from app.schemas.booking import BookingCreate, BookingResponse
from app.services.billing_service import calculate_booking_bill


router = APIRouter(prefix='/bookings', tags=['Bookings'])


def redis_owner_value(value):
    'Normalize Redis responses for both bytes and strings.'
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return value


def get_seat_lock_owner(key):
    'Read a seat-lock owner and handle Redis connection errors.'
    try:
        return redis_owner_value(redis_client.get(key))
    except Exception as exc:
        raise HTTPException(status_code=503,detail='Seat-lock service is temporarily unavailable') from exc


@router.post('', response_model=BookingResponse, status_code=201)
def create_booking(payload: BookingCreate,db: Session = Depends(get_db),user: User = Depends(require_roles('Customer'))):
    seat_ids = payload.seat_ids

    if not seat_ids:
        raise HTTPException(status_code=422,detail='Select at least one seat')

    if len(seat_ids) > 10:
        raise HTTPException(status_code=422,detail='A maximum of 10 seats can be booked at once')

    if len(seat_ids) != len(set(seat_ids)):
        raise HTTPException(status_code=422,detail='Duplicate seat IDs are not allowed')

    show = db.query(Show).filter(Show.id == payload.show_id).first()

    if show is None:
        raise HTTPException(status_code=404,detail='Show not found')

    if show.status != 'Scheduled':
        raise HTTPException(status_code=400,detail='This show is not available for booking')

    now = datetime.now()

    if show.booking_closes_at is None or now >= show.booking_closes_at:
        raise HTTPException(status_code=400,detail='Booking is closed for this show')

    seats = (db.query(Seat)
        .filter(Seat.id.in_(seat_ids),Seat.screen_id == show.screen_id,Seat.is_active.is_(True))
        .with_for_update()
        .all())

    if len(seats) != len(seat_ids):
        raise HTTPException(status_code=400,detail='One or more seats are invalid or inactive')

    lock_ttls = []
    for seat in seats:
        key = f"lock:show:{show.id}:seat:{seat.id}"
        owner = get_seat_lock_owner(key)

        if owner != str(user.id):
            raise HTTPException(status_code=409,detail=f"Seat {seat.id} is not locked by you or its lock has expired")
        try:
            ttl_ms = redis_client.pttl(key)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail='Seat-lock service is temporarily unavailable',
            ) from exc
        if ttl_ms <= 0:
            raise HTTPException(
                status_code=409,
                detail=f"Seat {seat.id} is not locked by you or its lock has expired",
            )
        lock_ttls.append(ttl_ms)

    # Prevent duplicate confirmed bookings.
    already_booked = (
        db.query(ConfirmedSeat.seat_id)
        .filter(ConfirmedSeat.show_id == show.id,
                ConfirmedSeat.seat_id.in_(seat_ids))
        .all())

    booked_ids = {row[0] for row in already_booked}

    if booked_ids:
        raise HTTPException(status_code=409,
            detail={'message': 'Some seats are already booked',
                    'seat_ids': sorted(booked_ids)})

    # Get seat category prices
    prices = (db.query(SeatCategoryPrice)
              .filter(SeatCategoryPrice.show_id == show.id)
              .all())

    price_by_category = {item.category: item.price for item in prices }

    if any( seat.category not in price_by_category for seat in seats ):
        raise HTTPException( status_code=400, detail='A price is missing for one or more seat categories')

    # Calculate bill using actual seat prices
    seat_prices = [price_by_category[seat.category] for seat in seats ]

    bill = calculate_booking_bill(seat_prices)

    if not isinstance(bill, dict):
        raise RuntimeError('Billing service must return a dictionary')

    required_fields = ('seat_count',
                       'ticket_total',
                       'convenience_fee',
                       'gst_amount',
                       'grand_total')

    if any(field not in bill for field in required_fields):
        raise RuntimeError('Billing service returned an incomplete bill')

    grand_total = Decimal(str(bill['grand_total']))

    if grand_total <= 0:
        raise HTTPException(status_code=400,detail='The calculated booking total must be positive')

    # Create pending booking
    booking = Booking(  booking_reference=f"BK-{uuid4().hex[:16].upper()}",
                        customer_id=user.id,
                        show_id=show.id,
                        total_amount=grand_total,
                        ticket_total=bill['ticket_total'],
                        convenience_fee=bill['convenience_fee'],
                        gst_amount=bill['gst_amount'],
                        grand_total=grand_total,
                        seat_count=bill['seat_count'],
                        status='Pending Payment',
                        expires_at=datetime.now() + timedelta(milliseconds=min(lock_ttls)))

    try:
        db.add(booking)
        db.flush()

        for seat in seats:
            db.add( BookingSeat(
                    booking_id=booking.id,
                    show_id=show.id,
                    seat_id=seat.id,
                    price=price_by_category[seat.category]))

        db.commit()
        db.refresh(booking)

    except Exception:
        db.rollback()
        raise

    return booking


@router.get('', response_model=list[BookingResponse])
def list_bookings(  status: Optional[str] = Query(None),
                    show_id: Optional[int] = Query(None, gt=0),
                    from_date: Optional[date] = Query(None),
                    to_date: Optional[date] = Query(None),
                    skip: int = Query(0, ge=0),
                    limit: int = Query(20, ge=1, le=100),
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles('Customer', 'Organizer', 'Admin'))):
  
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail='from_date cannot be after to_date')

    query = db.query(Booking).join(Show, Booking.show_id == Show.id)
    if user.role == 'Customer':
        query = query.filter(Booking.customer_id == user.id)
    elif user.role == 'Organizer':
        query = query.join(Event, Event.id == Show.event_id).filter(
            Event.organizer_id == user.id
        )

    if status:
        query = query.filter(Booking.status == status)
    if show_id is not None:
        query = query.filter(Booking.show_id == show_id)
    if from_date is not None:
        query = query.filter(Show.show_date >= from_date)
    if to_date is not None:
        query = query.filter(Show.show_date <= to_date)

    return (
        query.order_by(Booking.created_at.desc(), Booking.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get('/{booking_id}', response_model=BookingResponse)
def get_booking(booking_id: int,db: Session = Depends(get_db),
                user: User = Depends(require_roles('Customer', 'Organizer', 'Admin'))):
    
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
    return booking
