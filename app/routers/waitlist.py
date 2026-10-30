
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.booking import Booking, BookingSeat
from app.models.event import Show
from app.models.venue import Screen, Seat
from app.models.waitlist import Waitlist
from app.schemas.cancellation import WaitlistCreate, WaitlistResponse


router = APIRouter(tags=['Show Waitlist'])


@router.post('/shows/{show_id}/waitlist',response_model=WaitlistResponse,status_code=status.HTTP_201_CREATED)
def join_waitlist(show_id: int,payload: WaitlistCreate,db: Session = Depends(get_db),customer=Depends(require_roles('Customer'))):
    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    if show.status != 'Scheduled':
        raise HTTPException(status_code=400,detail='Waitlist is available only for scheduled shows')

    screen = db.query(Screen).filter(Screen.id == show.screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    category_seats = (
        db.query(Seat)
        .filter(Seat.screen_id == screen.id,
                Seat.category == payload.preferred_category,
                Seat.is_active.is_(True)).all())

    if not category_seats:
        raise HTTPException(status_code=400, detail='No active seats exist in this category')

    booked_seat_ids = (
        db.query(BookingSeat.seat_id)
        .join(Booking, Booking.id == BookingSeat.booking_id)
        .filter(Booking.show_id == show_id,Booking.status == 'Confirmed',
                BookingSeat.seat_id.in_([seat.id for seat in category_seats])).all())

    booked_ids = {row[0] for row in booked_seat_ids}

    available_count = sum(1 for seat in category_seats if seat.id not in booked_ids)

    if available_count >= payload.seat_count:
        raise HTTPException(status_code=409,detail='This show is not sold out for the requested category')

    existing_booking = ( db.query(Booking).filter(Booking.show_id == show_id,
                                                  Booking.customer_id == customer.id,
                                                  Booking.status.in_(['Pending', 'Pending Payment', 'Confirmed'])).first())

    if existing_booking:
        raise HTTPException(status_code=409,detail='You already have a booking for this show')

    existing_waitlist = (db.query(Waitlist)
                         .filter(Waitlist.show_id == show_id,Waitlist.customer_id == customer.id).first())

    if existing_waitlist:
        raise HTTPException(status_code=409,detail="You have already joined this show's waitlist")

    entry = Waitlist(show_id=show_id,
                     customer_id=customer.id,
                     seat_count=payload.seat_count,
                     preferred_category=payload.preferred_category)

    db.add(entry)

    try:
        db.commit()
        db.refresh(entry)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail="You have already joined this show's waitlist")

    return entry


@router.get('/shows/{show_id}/waitlist',response_model=list[WaitlistResponse])
def list_waitlist(show_id: int,skip: int = Query(0, ge=0),
                  limit: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db),
                  admin=Depends(require_roles('Admin'))):
   
    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    return (db.query(Waitlist)
            .filter(Waitlist.show_id == show_id)
            .order_by(Waitlist.created_at, Waitlist.id)
            .offset(skip)
            .limit(limit)
            .all())


@router.delete('/waitlist/{waitlist_id}')
def leave_waitlist(waitlist_id: int,db: Session = Depends(get_db),customer=Depends(require_roles('Customer'))):
    
    entry = (db.query(Waitlist).filter(Waitlist.id == waitlist_id).first())

    if entry is None:
        raise HTTPException(status_code=404, detail='Waitlist entry not found')

    if entry.customer_id != customer.id:
        raise HTTPException(status_code=403, detail='Access denied')

    db.delete(entry)
    db.commit()

    return {'message': 'You have left the waitlist successfully'}
