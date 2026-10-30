
import logging
from datetime import date,datetime, timedelta
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.utils.cache import (get_cache,set_cache,clear_event_cache)

from app.database import get_db
from app.auth.dependencies import get_current_user, require_roles
from app.models.user import User
from app.models.venue import Screen, Seat, Venue
from app.models.event import Event, Show, SeatCategoryPrice
from app.models.booking import Booking, BookingSeat, ConfirmedSeat, Payment
from app.models.refund import Refund
from app.models.user import User
from app.schemas.event import (EventCreate, EventUpdate, EventResponse,ShowCreate, ShowUpdate, ShowResponse)
from app.redis_client import redis_client
from app.services.email_service import send_show_cancelled
from app.websocket_manager import manager


from decimal import Decimal
from typing import Optional
from sqlalchemy import func


router = APIRouter(tags=['Events & Shows'])
logger = logging.getLogger(__name__)

GAP = timedelta(minutes=15)


def check_organizer(user):
    if user.role != 'Organizer' or not user.is_approved:
        raise HTTPException(status_code=403,detail='Only approved organizers can manage events')


def own_event(db, event_id, user):
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        raise HTTPException(404, 'Event not found')

    if user.role == 'Admin':
        return event

    check_organizer(user)

    if event.organizer_id != user.id:
        raise HTTPException(403, 'You do not own this event')

    return event


def get_categories(db, screen_id):
    return {category for (category,) in db.query(Seat.category).filter(Seat.screen_id == screen_id,Seat.is_active.is_(True)).distinct().all()}


def validate_prices(db, screen_id, prices):
    categories = get_categories(db, screen_id)

    if not categories:
        raise HTTPException(400, 'Screen has no active seats')

    provided = [p.category for p in prices]

    if len(provided) != len(set(provided)):
        raise HTTPException(422, 'Duplicate price categories')

    if set(provided) != categories:
        raise HTTPException(422,'Provide exactly one price for every active seat category: ' + ', '.join(sorted(categories)))


def calculate_times(show_date, start_time, duration):
    start = datetime.combine(show_date, start_time)
    end = start + timedelta(minutes=duration)

    if start <= datetime.now():
        raise HTTPException(400, 'Show must start in the future')

    return start, end, start - timedelta(minutes=30)


def check_overlap(db, screen_id, start, end, exclude_id=None):
    
    query = db.query(Show).filter(Show.screen_id == screen_id,
                                  Show.status != 'Cancelled',
                                  Show.start_time < end + GAP,
                                  Show.end_time + GAP > start)

    if exclude_id is not None:
        query = query.filter(Show.id != exclude_id)

    if query.first():
        raise HTTPException( 409,'Show overlaps another show or its 15-minute cleaning gap')


def lock_screen(db, screen_id):
    # Serialize scheduling operations for the same screen in MySQL.
    screen = db.query(Screen).filter( Screen.id == screen_id ).with_for_update().first()

    if screen is None:
        raise HTTPException(404, 'Screen not found')

    venue = db.query(Venue).filter( Venue.id == screen.venue_id ).first()

    if venue is None or not venue.is_active:
        raise HTTPException(400, 'Venue is inactive')

    return screen


def set_prices(show, prices):
    show.prices = [ SeatCategoryPrice(category=p.category, price=p.price) for p in prices ]


@router.post('/events', response_model=EventResponse, status_code=201)
def create_event(payload: EventCreate,db: Session = Depends(get_db),user: User = Depends(require_roles('Organizer'))):
    check_organizer(user)

    event = Event(organizer_id=user.id,**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    clear_event_cache()
    return event




@router.get('/events', response_model=List[EventResponse])
def list_events(search: Optional[str] = Query(None),
                city: Optional[str] = Query(None),
                category: Optional[str] = Query(None),
                language: Optional[str] = Query(None),
                show_date: Optional[date] = Query(None),
                from_date: Optional[date] = Query(None),
                to_date: Optional[date] = Query(None),
                min_price: Optional[Decimal] = Query(None, ge=0),
                max_price: Optional[Decimal] = Query(None, ge=0),
                sort_by: str = Query('newest',pattern='^(newest|oldest|title|date|price)$'),
                order: str = Query('asc', pattern='^(asc|desc)$'),
                skip: int = Query(0, ge=0),
                limit: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    
    if (min_price is not None
        and max_price is not None
        and min_price > max_price):
        raise HTTPException(status_code=422,detail='min_price cannot exceed max_price')

    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail='from_date cannot be after to_date')

    cache_key = (f"events:list:{user.role}:{user.id}:"
                 f"{search}:{city}:{category}:{language}:"
                 f"{show_date}:{from_date}:{to_date}:{min_price}:{max_price}:"
                 f"{sort_by}:{order}:{skip}:{limit}")

    cached = get_cache(cache_key)

    if cached is not None:
        return cached

    query = db.query(Event)

    # Role-based visibility
    if user.role in ('Customer', 'Staff'):
        query = query.filter(Event.status == 'Published')

    elif user.role == 'Organizer':
        query = query.filter(Event.organizer_id == user.id)

    elif user.role != 'Admin':
        raise HTTPException(status_code=403,detail='Role not allowed')

    # Search by event title
    if search:
        query = query.filter(Event.title.ilike(f"%{search.strip()}%"))

    # Filter by category
    if category:
        query = query.filter(Event.category.ilike(category.strip()))

    # Filter by language
    if language:
        query = query.filter(Event.language.ilike(language.strip()))

    # Build a single show-level query so date, city and price
    # conditions apply to the same show.
    matching_shows = (db.query(Show.event_id)
                      .join(Screen, Show.screen_id == Screen.id)
                      .join(Venue, Screen.venue_id == Venue.id)
                      .filter(Show.status != 'Cancelled'))

    has_show_filter = False

    if show_date is not None:
        matching_shows = matching_shows.filter(Show.show_date == show_date)
        has_show_filter = True

    if from_date is not None:
        matching_shows = matching_shows.filter(Show.show_date >= from_date)
        has_show_filter = True

    if to_date is not None:
        matching_shows = matching_shows.filter(Show.show_date <= to_date)
        has_show_filter = True

    if city:
        matching_shows = matching_shows.filter(Venue.city.ilike(city.strip()),Venue.is_active.is_(True))
        has_show_filter = True

    if min_price is not None or max_price is not None:
        matching_shows = matching_shows.join(SeatCategoryPrice,SeatCategoryPrice.show_id == Show.id)

        if min_price is not None:
            matching_shows = matching_shows.filter(SeatCategoryPrice.price >= min_price)

        if max_price is not None:
            matching_shows = matching_shows.filter(SeatCategoryPrice.price <= max_price)

        has_show_filter = True

    if has_show_filter:
        query = query.filter(Event.id.in_(matching_shows))

    # Sorting
    if sort_by == 'oldest':
        query = query.order_by(Event.id.asc())

    elif sort_by == 'title':
        query = query.order_by(
            Event.title.desc() if order == 'desc' else Event.title.asc(),
            Event.id.desc() if order == 'desc' else Event.id.asc(),
        )

    elif sort_by == 'date':
        earliest_show = (db.query(func.min(Show.start_time))
                         .filter(Show.event_id == Event.id,Show.status != 'Cancelled')
                         .correlate(Event)
                         .scalar_subquery())

        direction = (
            'desc' if sort_by == 'newest' else order
        )
        query = query.order_by(
            earliest_show.desc() if direction == 'desc' else earliest_show.asc(),
            Event.id.desc() if direction == 'desc' else Event.id.asc(),
        )

    elif sort_by == 'price':
        lowest_price = (db.query(func.min(SeatCategoryPrice.price))
                        .join(Show,SeatCategoryPrice.show_id == Show.id)
                        .filter(Show.event_id == Event.id,Show.status != 'Cancelled')
                        .correlate(Event)
                        .scalar_subquery())

        query = query.order_by(
            lowest_price.desc() if order == 'desc' else lowest_price.asc(),
            Event.id.desc() if order == 'desc' else Event.id.asc(),
        )

    else:
        query = query.order_by(Event.id.desc())

    events = query.offset(skip).limit(limit).all()

    result = [EventResponse.model_validate(event).model_dump(mode='json') for event in events ]

    set_cache(cache_key, result)

    return result


@router.get('/events/{event_id}', response_model=EventResponse)
def get_event(event_id: int,db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    cache_key = f"events:detail:{event_id}:{user.role}:{user.id}"

    cached = get_cache(cache_key)

    if cached is not None:
        return cached

    event = (db.query(Event).filter(Event.id == event_id).first())

    if event is None:
        raise HTTPException(404, 'Event not found')

    if event.status != 'Published':
        if user.role != 'Admin' and not (user.role == 'Organizer' and event.organizer_id == user.id ):
            raise HTTPException(404, 'Event not found')

    result = EventResponse.model_validate(event).model_dump(mode='json')

    set_cache(cache_key, result)

    return result


@router.put('/events/{event_id}', response_model=EventResponse)
def update_event( event_id: int,payload: EventUpdate,db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    event = own_event(db, event_id, user)
    changes = payload.model_dump(exclude_unset=True)

    if any(value is None and key != 'description' for key, value in changes.items()):
        raise HTTPException(422, 'Required event fields cannot be null')

    if event.status == 'Cancelled':
        raise HTTPException(409, 'Cancelled events cannot be updated')

    if changes.get('status') == 'Cancelled':
        raise HTTPException(409, 'Use the show cancellation endpoint for shows')

    if ('duration_minutes' in changes
        and changes['duration_minutes'] != event.duration_minutes
        and db.query(Show).filter(Show.event_id == event.id).first()):
        raise HTTPException( 409, 'Cannot change duration after shows are scheduled')

    for key, value in changes.items():
        setattr(event, key, value)

    db.commit()
    db.refresh(event)
    clear_event_cache()
    return event


@router.post('/events/{event_id}/shows',response_model=ShowResponse,status_code=201)
def create_show(event_id: int,payload: ShowCreate,db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    event = own_event(db, event_id, user)

    if event.status != 'Published':
        raise HTTPException(400, 'Publish the event before scheduling')

    try:
        lock_screen(db, payload.screen_id)
        validate_prices(db, payload.screen_id, payload.prices)

        start, end, closes = calculate_times( payload.show_date, payload.start_time,
            event.duration_minutes )
        check_overlap(db, payload.screen_id, start, end)

        show = Show(event_id=event.id,screen_id=payload.screen_id,show_date=payload.show_date,
                    start_time=start,end_time=end,booking_closes_at=closes,status='Scheduled')
        set_prices(show, payload.prices)

        db.add(show)
        db.commit()
        db.refresh(show)
        clear_event_cache()
        return show
    except Exception:
        db.rollback()
        raise


@router.get('/events/{event_id}/shows',response_model=List[ShowResponse])
def list_shows(event_id: int,
               show_date: Optional[date] = Query(None),
               skip: int = Query(0, ge=0),
               limit: int = Query(20, ge=1, le=100),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
   
    event = (db.query(Event).filter(Event.id == event_id).first())

    if event is None:
        raise HTTPException(404, 'Event not found')

    if event.status != 'Published' and user.role != 'Admin':
        if user.role != 'Organizer' or event.organizer_id != user.id:
            raise HTTPException(404, 'Event not found')

    query = db.query(Show).filter(Show.event_id == event_id)

    if show_date: query = query.filter( Show.show_date == show_date )

    return ( query.order_by(Show.start_time, Show.id).offset(skip).limit(limit).all())


@router.put('/shows/{show_id}', response_model=ShowResponse)
def update_show( show_id: int,payload: ShowUpdate,db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(404, 'Show not found')

    event = own_event(db, show.event_id, user)

    if event.status != 'Published' or show.status != 'Scheduled':
        raise HTTPException(409, 'Show cannot be updated')

    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, 'Show fields cannot be null')

    screen_id = changes.get('screen_id', show.screen_id)
    show_date = changes.get('show_date', show.show_date)
    start_time = changes.get('start_time', show.start_time.time())

    try:
        # Lock both screens in stable order if moving a show.
        for sid in sorted(set([show.screen_id, screen_id])):
            lock_screen(db, sid)

        prices = payload.prices

        if prices is None:
            prices = list(show.prices)
        elif db.query(Booking.id).filter(
            Booking.show_id == show.id, Booking.status == 'Confirmed'
        ).first():
            raise HTTPException(
                status_code=409,
                detail='Seat prices cannot be changed after a confirmed booking',
            )

        validate_prices(db, screen_id, prices)

        start, end, closes = calculate_times(show_date, start_time, event.duration_minutes)
        check_overlap(db, screen_id, start, end, show.id)

        show.screen_id = screen_id
        show.show_date = show_date
        show.start_time = start
        show.end_time = end
        show.booking_closes_at = closes

        if payload.prices is not None:
            set_prices(show, payload.prices)

        db.commit()
        db.refresh(show)
        clear_event_cache()
        return show
    except Exception:
        db.rollback()
        raise


@router.put('/shows/{show_id}/cancel', response_model=ShowResponse)
def cancel_show(
    show_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(404, 'Show not found')

    event = own_event(db, show.event_id, user)

    if show.status != 'Scheduled':
        raise HTTPException(409, 'Only scheduled shows can be cancelled')

    bookings = (
        db.query(Booking)
        .filter(
            Booking.show_id == show_id,
            Booking.status.in_(('Confirmed', 'Pending', 'Pending Payment')),
        )
        .with_for_update()
        .all()
    )
    notices = []
    released_seats = set()
    for booking in bookings:
        seat_ids = {
            row[0]
            for row in db.query(BookingSeat.seat_id)
            .filter(BookingSeat.booking_id == booking.id)
            .all()
        }
        released_seats.update(seat_ids)
        db.query(ConfirmedSeat).filter(
            ConfirmedSeat.booking_id == booking.id
        ).delete(synchronize_session=False)
        if booking.status == 'Confirmed':
            payment = (
                db.query(Payment)
                .filter(
                    Payment.booking_id == booking.id,
                    Payment.status.in_(('Success', 'Paid')),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Confirmed booking {booking.booking_reference} has no successful payment",
                )
            payment.status = 'Refunded'
            db.add(
                Refund(
                    booking_id=booking.id,
                    payment_id=payment.id,
                    amount=payment.amount,
                    reason='Show Cancellation',
                    status='Refunded',
                )
            )
            customer = db.query(User).filter(User.id == booking.customer_id).first()
            if customer is not None:
                notices.append(
                    (
                        customer.email,
                        booking.booking_reference,
                        str(payment.amount),
                    )
                )
        booking.status = 'Cancelled'

    show.status = 'Cancelled'
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    for email, booking_reference, refund_amount in notices:
        background_tasks.add_task(
            send_show_cancelled,
            email,
            event.title,
            booking_reference,
            refund_amount,
        )
    try:
        for key in redis_client.scan_iter(match=f"lock:show:{show_id}:seat:*"):
            seat_id = int(key.rsplit(':', 1)[1])
            redis_client.delete(key)
            released_seats.add(seat_id)
    except Exception:
        logger.exception('Could not clear Redis locks for cancelled show %s', show_id)

    for seat_id in released_seats:
        manager.broadcast_sync(
            show_id,
            {'type': 'seat_update', 'seat_id': seat_id, 'status': 'Available'},
        )
    manager.broadcast_sync(
        show_id,
        {
            'type': 'show_cancelled',
            'show_id': show_id,
            'message': 'This show has been cancelled',
        },
    )
    clear_event_cache()
    db.refresh(show)
    return show
