
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.booking import Booking, BookingSeat, Payment
from app.models.event import Event, Show
from app.models.ticket import TicketScan
from app.models.user import User
from app.models.venue import Venue, Screen, Seat
from app.schemas.ticket import (TicketScanRequest, TicketScanResponse,ShowEntriesResponse)
from app.services.ticket_service import (generate_ticket_pdf,verify_ticket_signature)


router = APIRouter(tags=['Tickets & QR Code Entry'])


def get_show_datetime(show_date, show_time):

    if isinstance(show_date, datetime):
        show_date = show_date.date()

    if isinstance(show_time, datetime):
        show_time = show_time.time()

    return datetime.combine(show_date, show_time)


def get_booking_seats(db: Session, booking_id: int):

    seats = (db.query(Seat)
             .join(BookingSeat, BookingSeat.seat_id == Seat.id)
             .filter(BookingSeat.booking_id == booking_id)
             .order_by(Seat.row_label, Seat.seat_number)
             .all())

    return [f"{seat.row_label}{seat.seat_number}" for seat in seats]


@router.get('/bookings/{booking_id}/ticket')
def download_ticket(booking_id: int,db: Session = Depends(get_db),
                    current_user=Depends(require_roles('Customer', 'Organizer', 'Admin'))):

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')

    if booking.status != 'Confirmed':
        raise HTTPException(status_code=409,
                            detail='Ticket is available only for confirmed bookings')

    show = db.query(Show).filter(Show.id == booking.show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    event = db.query(Event).filter(Event.id == show.event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail='Event not found')

    if current_user.role == 'Customer' and booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail='You can download only your own tickets')

    if current_user.role == 'Organizer' and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403, detail='You cannot access this booking')

    screen = db.query(Screen).filter(Screen.id == show.screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    venue = db.query(Venue).filter(Venue.id == screen.venue_id).first()

    if venue is None:
        raise HTTPException(status_code=404, detail='Venue not found')

    customer = db.query(User).filter(User.id == booking.customer_id).first()

    if customer is None:
        raise HTTPException(status_code=404, detail='Customer not found')

    payment = (db.query(Payment)
               .filter(Payment.booking_id == booking.id,
                       Payment.status.in_(['Paid', 'Success']))
               .first())

    if payment is None:
        raise HTTPException(status_code=409,
                            detail='Successful payment not found')

    seats = get_booking_seats(db, booking.id)

    file_path = generate_ticket_pdf(booking_number=booking.booking_reference,
                                    event_title=event.title,
                                    venue_name=venue.name,
                                    screen_name=screen.name,
                                    show_date=str(show.show_date),
                                    show_time=str(show.start_time),
                                    seats=seats,
                                    amount_paid=str(payment.amount),
        customer_name=customer.full_name)

    return FileResponse(file_path,media_type='application/pdf',
                        filename=f"{booking.booking_reference}.pdf")


@router.post('/tickets/scan',response_model=TicketScanResponse,
             status_code=status.HTTP_200_OK)
def scan_ticket(payload: TicketScanRequest,db: Session = Depends(get_db),
                staff=Depends(require_roles('Staff'))):

    valid_signature = verify_ticket_signature(payload.booking_number,
                                              payload.signature)

    if not valid_signature:
        raise HTTPException(status_code=400, detail='Invalid QR code signature')

    booking = (db.query(Booking)
               .filter(Booking.booking_reference == payload.booking_number)
               .with_for_update()
               .first())

    if booking is None:
        raise HTTPException(status_code=404, detail='Booking not found')

    if booking.status != 'Confirmed':
        raise HTTPException(status_code=409,
                            detail='Cancelled, expired or unconfirmed tickets cannot be scanned')

    show = db.query(Show).filter(Show.id == booking.show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    if show.status == 'Cancelled':
        raise HTTPException(status_code=409, detail='This show has been cancelled')

    screen = db.query(Screen).filter(Screen.id == show.screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    if staff.venue_id != screen.venue_id:
        raise HTTPException(status_code=403,
                            detail='You can scan tickets only at your assigned venue')

    start_datetime = get_show_datetime(show.show_date, show.start_time)
    end_datetime = get_show_datetime(show.show_date, show.end_time)

    if end_datetime <= start_datetime:
        end_datetime += timedelta(days=1)

    current_datetime = datetime.now()

    if current_datetime < start_datetime - timedelta(hours=1):
        raise HTTPException(status_code=400,
                            detail='Ticket scanning opens one hour before the show')

    if current_datetime > end_datetime:
        raise HTTPException(status_code=400,
                            detail='Ticket scanning is closed for this show')

    existing_scan = (db.query(TicketScan)
                     .filter(TicketScan.booking_id == booking.id)
                     .first())

    if existing_scan is not None:
        raise HTTPException(status_code=409,
                            detail=f"Ticket already used at {existing_scan.scanned_at}")

    customer = db.query(User).filter(User.id == booking.customer_id).first()

    if customer is None:
        raise HTTPException(status_code=404, detail='Customer not found')

    seats = get_booking_seats(db, booking.id)

    ticket_scan = TicketScan(booking_id=booking.id,staff_id=staff.id)

    db.add(ticket_scan)

    try:
        db.commit()
        db.refresh(ticket_scan)

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail='Ticket already used')

    return TicketScanResponse(message='Ticket scanned successfully',
                              booking_number=booking.booking_reference,
                              customer_name=customer.full_name,
                              seats=seats,
                              seat_count=len(seats),
                              scanned_at=ticket_scan.scanned_at.isoformat())


@router.get('/shows/{show_id}/entries',response_model=ShowEntriesResponse)
def get_show_entries(show_id: int,db: Session = Depends(get_db),
                     current_user=Depends(require_roles('Admin', 'Organizer', 'Staff'))):

    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    event = db.query(Event).filter(Event.id == show.event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail='Event not found')

    screen = db.query(Screen).filter(Screen.id == show.screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    if current_user.role == 'Organizer' and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403,
                            detail='You can view entries only for your own events')

    if current_user.role == 'Staff' and current_user.venue_id != screen.venue_id:
        raise HTTPException(status_code=403,
                            detail='You can view entries only for your assigned venue')

    confirmed_bookings = (db.query(Booking)
                          .filter(Booking.show_id == show_id,
                                  Booking.status == 'Confirmed')
                          .count())

    entered_bookings = (db.query(TicketScan)
                        .join(Booking, Booking.id == TicketScan.booking_id)
                        .filter(Booking.show_id == show_id,
                                Booking.status == 'Confirmed')
                        .count())

    remaining_bookings = max(confirmed_bookings - entered_bookings, 0)

    return ShowEntriesResponse( show_id=show_id,confirmed_bookings=confirmed_bookings,
                                entered_bookings=entered_bookings,remaining_bookings=remaining_bookings )
