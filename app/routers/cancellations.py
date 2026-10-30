
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.booking import Booking, BookingSeat, ConfirmedSeat, Payment
from app.models.event import Event, Show
from app.models.refund import Refund
from app.models.venue import Screen
from app.models.user import User
from app.schemas.cancellation import RefundResponse, CancellationResponse
from app.services.refund_service import calculate_customer_refund
from app.redis_client import redis_client
from app.services.email_service import send_booking_cancelled
from app.services.notifications import notify_waitlisted_customers
from app.websocket_manager import manager


router = APIRouter(tags=['Cancellations & Refunds'])


@router.put('/bookings/{booking_id}/cancel',response_model=CancellationResponse)
def cancel_booking(booking_id: int,background_tasks: BackgroundTasks,
                   db: Session = Depends(get_db),
                   current_user=Depends(require_roles('Customer'))):
    booking = (db.query(Booking).filter(Booking.id == booking_id).with_for_update().first())

    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')

    if booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail='Access denied')

    if booking.status != 'Confirmed':
        raise HTTPException(status_code=409,detail='Only confirmed bookings can be cancelled')

    show = db.query(Show).filter(Show.id == booking.show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    show_start = datetime.combine(show.show_date, show.start_time)

    if show_start <= datetime.now():
        raise HTTPException(
            status_code=400,
            detail='Cancellation is not allowed after the show starts'
        )

    try:
        refund_amount = calculate_customer_refund(Decimal(str(booking.ticket_total)),show_start)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    payment = (db.query(Payment).filter(Payment.booking_id == booking.id,Payment.status.in_(['Paid', 'Success'])).first())

    if payment is None:
        raise HTTPException(status_code=409,detail='Successful payment not found')

    refund = Refund(booking_id=booking.id,payment_id=payment.id,amount=refund_amount,
                    reason='Customer Cancellation',status='Refunded')

    booking.status = 'Cancelled'

    # Mock refund: mark the payment refunded.
    # A real gateway must process the actual money refund.
    payment.status = 'Refunded'

    seat_ids = [
        row[0]
        for row in db.query(BookingSeat.seat_id)
        .filter(BookingSeat.booking_id == booking.id)
        .all()
    ]
    db.query(ConfirmedSeat).filter(
        ConfirmedSeat.booking_id == booking.id
    ).delete(synchronize_session=False)
    db.add(refund)

    try:
        db.commit()
        db.refresh(refund)
    except Exception:
        db.rollback()
        raise

    background_tasks.add_task(
        send_booking_cancelled,
        current_user.email,
        booking.booking_reference,
        str(refund_amount),
    )
    for seat_id in seat_ids:
        manager.broadcast_sync(
            booking.show_id,
            {'type': 'seat_update', 'seat_id': seat_id, 'status': 'Available'},
        )
    notify_waitlisted_customers(db, booking.show_id, seat_ids, background_tasks)

    return CancellationResponse(message='Booking cancelled successfully',booking_id=booking.id,
                                booking_status=booking.status,refund_amount=refund_amount)


@router.get('/bookings/{booking_id}/refunds',response_model=list[RefundResponse])
def get_booking_refunds(booking_id: int,db: Session = Depends(get_db),current_user=Depends(get_current_user)):
    
    booking = (db.query(Booking).filter(Booking.id == booking_id).first())

    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')

    if current_user.role == 'Customer':
        if booking.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail='Access denied')

    elif current_user.role == 'Organizer':
        show = db.query(Show).filter(Show.id == booking.show_id).first()

        event = db.query(Event).filter(Event.id == show.event_id).first()

        if event.organizer_id != current_user.id:
            raise HTTPException(status_code=403, detail='Access denied')

    elif current_user.role != 'Admin':
        raise HTTPException(status_code=403, detail='Access denied')

    return (db.query(Refund).filter(Refund.booking_id == booking_id).order_by(Refund.refunded_at.desc()).all())
