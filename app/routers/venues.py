
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.venue import Venue, Screen, Seat
from app.schemas.venue import (VenueCreate,VenueUpdate,VenueResponse,ScreenCreate,ScreenResponse,
                               BulkSeatCreate,SeatResponse,ScreenLayoutResponse,SeatRowLayout,SeatStatusUpdate)


router = APIRouter(tags=['Venue, Screen & Seat Management'])


def require_admin():
    return Depends(require_roles('Admin'))


@router.post('/venues',response_model=VenueResponse,status_code=status.HTTP_201_CREATED)
def create_venue(payload: VenueCreate,db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
   
    venue = Venue(**payload.model_dump())
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue


@router.get('/venues', response_model=list[VenueResponse])
def list_venues(db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
    return db.query(Venue).order_by(Venue.id).all()


@router.put('/venues/{venue_id}', response_model=VenueResponse)
def update_venue(venue_id: int,payload: VenueUpdate,db: Session = Depends(get_db),
                 admin=Depends(require_roles('Admin'))):

    venue = db.query(Venue).filter(Venue.id == venue_id).first()

    if venue is None:
        raise HTTPException(status_code=404, detail='Venue not found')

    changes = payload.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(venue, field, value)

    db.commit()
    db.refresh(venue)
    return venue


@router.post('/venues/{venue_id}/screens',response_model=ScreenResponse,status_code=status.HTTP_201_CREATED)
def create_screen(venue_id: int,payload: ScreenCreate,db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()

    if venue is None:
        raise HTTPException(status_code=404, detail='Venue not found')

    if not venue.is_active:
        raise HTTPException(status_code=400,detail='Cannot add a screen to an inactive venue')

    screen = Screen(venue_id=venue_id,name=payload.name,total_seats=0)
    db.add(screen)

    try:
        db.commit()
        db.refresh(screen)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail='A screen with this name already exists at this venue' )

    return screen


@router.post('/screens/{screen_id}/seats/bulk',status_code=status.HTTP_201_CREATED )
def create_seats_bulk(screen_id: int,payload: BulkSeatCreate,db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
    screen = db.query(Screen).filter(Screen.id == screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    venue = db.query(Venue).filter(Venue.id == screen.venue_id).first()
    if venue is None or not venue.is_active:
        raise HTTPException( status_code=400,detail='Cannot add seats to a screen at an inactive venue' )

    row_labels = [row.row_label.strip().upper() for row in payload.rows]

    if any(not label for label in row_labels):
        raise HTTPException(status_code=422, detail='Row labels cannot be empty')

    if len(row_labels) != len(set(row_labels)):
        raise HTTPException(status_code=422,detail='Each row_label must appear only once in a bulk request')

    existing_seats = (db.query(Seat).filter(Seat.screen_id == screen_id,Seat.row_label.in_(row_labels)).all())

    existing_positions = {(seat.row_label, seat.seat_number)for seat in existing_seats}

    new_seats = []

    for row in payload.rows:
        row_label = row.row_label.strip().upper()

        for seat_number in range(1, row.seat_count + 1):
            if (row_label, seat_number) in existing_positions:
                raise HTTPException(
                    status_code=409,
                    detail=(f"Seat {row_label}{seat_number} already exists "f"on screen {screen_id}"))

            new_seats.append(
                Seat(screen_id=screen_id,row_label=row_label,seat_number=seat_number,category=row.category,is_active=True))

    try:
        db.add_all(new_seats)
        db.flush()

        screen.total_seats = (db.query(Seat).filter(Seat.screen_id == screen_id).count())

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail='Duplicate seat position detected')

    return { 'message': 'Seats created successfully','screen_id': screen_id,
             'created_seats': len(new_seats),'total_seats': screen.total_seats }


@router.get('/screens/{screen_id}/layout',response_model=ScreenLayoutResponse)
def get_screen_layout(screen_id: int,db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
    screen = db.query(Screen).filter(Screen.id == screen_id).first()

    if screen is None:
        raise HTTPException(status_code=404, detail='Screen not found')

    seats = ( db.query(Seat).filter(Seat.screen_id == screen_id).order_by(Seat.row_label, Seat.seat_number).all())

    grouped = defaultdict(list)

    for seat in seats:
        grouped[seat.row_label].append(seat)

    rows = [SeatRowLayout(row_label=row_label, seats=row_seats) for row_label, row_seats in sorted(grouped.items())]

    return ScreenLayoutResponse(screen_id=screen.id,screen_name=screen.name,
                                venue_id=screen.venue_id,total_seats=screen.total_seats,
                                rows=rows)


@router.put('/seats/{seat_id}/status', response_model=SeatResponse)
def update_seat_status(seat_id: int,payload: SeatStatusUpdate,db: Session = Depends(get_db),admin=Depends(require_roles('Admin'))):
   
    seat = db.query(Seat).filter(Seat.id == seat_id).first()

    if seat is None:
        raise HTTPException(status_code=404, detail='Seat not found')

    seat.is_active = payload.is_active
    db.commit()
    db.refresh(seat)

    return seat
