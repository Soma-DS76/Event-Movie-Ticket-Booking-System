import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.event import Show, SeatCategoryPrice
from app.models.booking import Booking, ConfirmedSeat
from app.models.venue import Seat
from app.redis_client import redis_client
from app.schemas.seat_lock import (SeatLockRequest,SeatMapResponse,SeatMapItem,SeatLockResponse,SeatUnlockResponse)
from app.services.seat_map_service import build_seat_map
from app.websocket_manager import manager

from app.utils.rate_limit import check_rate_limit

router = APIRouter(tags=['Seat Locking'])
logger = logging.getLogger(__name__)

LOCK_SECONDS = 600
MAX_SEATS_PER_SHOW = 10


def get_show_or_404(db: Session, show_id: int) -> Show:
    show = db.query(Show).filter(Show.id == show_id).first()

    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    return show


def seat_lock_key(show_id: int, seat_id: int) -> str:
    return 'lock:show:{}:seat:{}'.format(show_id, seat_id)


def get_show_seats(db: Session, show: Show):
    return ( db.query(Seat)
        .filter(Seat.screen_id == show.screen_id)
        .order_by(Seat.row_label, Seat.seat_number)
        .all())


def get_prices(show: Show) -> Dict[str, float]:
    return { price.category: float(price.price) for price in show.prices }


def get_locked_seats(show_id: int) -> Dict[int, str]:
    locked = {}

    pattern = 'lock:show:{}:seat:*'.format(show_id)

    for key in redis_client.scan_iter(match=pattern, count=100):
        value = redis_client.get(key)

        if value is None:
            continue

        try:
            seat_id = int(key.rsplit(':', 1)[1])
        except (ValueError, IndexError):
            continue

        locked[seat_id] = value

    return locked


def ensure_locking_allowed(show: Show):
    if show.status != 'Scheduled':
        raise HTTPException(status_code=409,detail='Seats can only be locked for scheduled shows',)

    if datetime.now() >= show.booking_closes_at:
        raise HTTPException(status_code=409,detail='Seat locking is closed for this show')


def validate_no_single_empty_seat(seats: List[Seat],occupied_ids: Set[int]):
    '\n    Reject a layout where an available seat is trapped between\n    two occupied seats in the same row.\n    '
    rows = {}

    for seat in seats:
        if not seat.is_active:
            continue

        rows.setdefault(seat.row_label, []).append(seat)

    for row_seats in rows.values():
        row_seats.sort(key=lambda seat: seat.seat_number)

        for index in range(1, len(row_seats) - 1):
            previous_seat = row_seats[index - 1]
            current_seat = row_seats[index]
            next_seat = row_seats[index + 1]

            if (previous_seat.seat_id if hasattr(previous_seat, 'seat_id')
                else previous_seat.id ) in occupied_ids and ( 
                    next_seat.id in occupied_ids ) and current_seat.id not in occupied_ids:
                raise HTTPException(
                    status_code=409,
                    detail={'message': (
                            'Selection would leave one empty seat '
                            'between occupied seats'),
                        'seat_id': current_seat.id,
                        'row': current_seat.row_label})


@router.get('/shows/{show_id}/seats',response_model=SeatMapResponse)
def get_seat_map(show_id: int,db: Session = Depends(get_db),user: User = Depends(require_roles('Customer'))):
    return SeatMapResponse(show_id=show_id,seats=build_seat_map(db, show_id, user.id))


@router.post('/shows/{show_id}/lock-seats',response_model=SeatLockResponse)
def lock_seats(show_id: int,payload: SeatLockRequest,db: Session = Depends(get_db),user: User = Depends(require_roles('Customer'))):
    try:
        check_rate_limit(f"rate:seat-lock:{user.id}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Rate-limiting service is temporarily unavailable') from exc

    show = get_show_or_404(db, show_id)
    ensure_locking_allowed(show)

    requested_ids = payload.seat_ids

    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=422,detail='Duplicate seat IDs are not allowed')

    try:
        seats = get_show_seats(db, show)
        seats_by_id = {seat.id: seat for seat in seats}

        invalid_ids = [seat_id
                       for seat_id in requested_ids
                       if seat_id not in seats_by_id ]

        if invalid_ids:
            raise HTTPException(status_code=404,
                                detail={ 'message': "Some seats do not belong to this show's screen",'seat_ids': invalid_ids})

        inactive_ids = [seat_id
            for seat_id in requested_ids
            if not seats_by_id[seat_id].is_active]

        if inactive_ids:
            raise HTTPException(status_code=409,detail={
                    'message': 'Some seats are unavailable',
                    'seat_ids': inactive_ids})

        current_locks = get_locked_seats(show_id)
        booked_ids = {row[0] for row in db.query(ConfirmedSeat.seat_id)
            .filter(ConfirmedSeat.show_id == show_id)
            .all()}

        # Count the customer's existing locks for this show.
        customer_locked_ids = {seat_id for seat_id, owner_id in current_locks.items() if owner_id == str(user.id)}

        requested_set = set(requested_ids)
        already_confirmed = {
            row[0]
            for row in (
                db.query(ConfirmedSeat.seat_id)
                .join(Booking, Booking.id == ConfirmedSeat.booking_id)
                .filter(ConfirmedSeat.show_id == show_id,
                        Booking.customer_id == user.id)
                .all())}
       
        total_seats = customer_locked_ids | requested_set | already_confirmed

        if len(total_seats) > MAX_SEATS_PER_SHOW:
            raise HTTPException( status_code=409, detail='A customer can lock at most 10 seats per show' )

        unavailable_ids = [
            seat_id
            for seat_id in requested_ids
            if seat_id in booked_ids
            or (seat_id in current_locks
                and current_locks[seat_id] != str(user.id))]

        if unavailable_ids:
            raise HTTPException(status_code=409,
                                detail={'message': 'Some seats are already locked','seat_ids': unavailable_ids})

        # Include other customers' locks and this request's selected seats
        # when checking for a single empty seat.
        occupied_ids = set(current_locks.keys()) | booked_ids | requested_set

        validate_no_single_empty_seat(seats, occupied_ids)

        acquired_keys = []

        try:
            for seat_id in requested_ids:
                key = seat_lock_key(show_id, seat_id)

                # Refresh the TTL for an existing lock owned by this customer.
                if current_locks.get(seat_id) == str(user.id):
                    if redis_client.expire(key, LOCK_SECONDS):
                        continue

                acquired = redis_client.set(key,str(user.id),nx=True,ex=LOCK_SECONDS)

                if not acquired:
                    raise HTTPException( status_code=409,detail={
                        'message': 'Seat was locked by another customer',
                        'seat_ids': [seat_id]})

                acquired_keys.append(key)

        except Exception:
            # Roll back every lock created by this request.
            for key in acquired_keys:
                try:
                    if redis_client.get(key) == str(user.id):
                        redis_client.delete(key)
                except Exception:
                    logger.exception('Could not roll back seat lock %s', key)
            raise

        try:
            ttls = [redis_client.pttl(seat_lock_key(show_id, seat_id)) for seat_id in requested_ids]
       
        except Exception as exc:
            raise HTTPException(status_code=503,detail='Seat-locking service is temporarily unavailable') from exc
       
        if len(ttls) != len(requested_ids) or any(ttl <= 0 for ttl in ttls):
            for key in acquired_keys:
                try:
                    if redis_client.get(key) == str(user.id):
                        redis_client.delete(key)
                except Exception:
                    logger.exception('Could not roll back expired seat lock %s', key)
            raise HTTPException(status_code=409,detail='One or more seat locks expired before completion')
      
        expiry_ms = min(ttls)
        expires_at = datetime.now() + timedelta(milliseconds=expiry_ms)
        for seat_id in requested_ids:
            manager.broadcast_sync(
                show_id,{  'type': 'seat_update',
                            'seat_id': seat_id,
                            'status': 'Locked',
                            '_owner_id': user.id})

        return SeatLockResponse( message='Seats locked successfully',
                                show_id=show_id,
                                seat_ids=requested_ids,
                                expires_in_seconds=max(1, expiry_ms // 1000),
                                expires_at=expires_at)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503,detail='Unable to lock seats because the seat-locking service failed')


@router.delete('/shows/{show_id}/lock-seats',response_model=SeatUnlockResponse )
def unlock_seats(show_id: int,payload: SeatLockRequest,db: Session = Depends(get_db),user: User = Depends(require_roles('Customer'))):
   
    show = get_show_or_404(db, show_id)
    seats = get_show_seats(db, show)
    valid_ids = {seat.id for seat in seats}

    if len(payload.seat_ids) != len(set(payload.seat_ids)):
        raise HTTPException(status_code=422, detail='Duplicate seat IDs are not allowed' )

    invalid_ids = [seat_id for seat_id in payload.seat_ids 
                   if seat_id not in valid_ids ]

    if invalid_ids:
        raise HTTPException( status_code=404, detail={
                'message': "Some seats do not belong to this show's screen",
                'seat_ids': invalid_ids})

    released_ids = []
    release_script = "\n    if redis.call('GET', KEYS[1]) == ARGV[1] then\n        return redis.call('DEL', KEYS[1])\n    end\n    return 0\n    "

    try:
        for seat_id in payload.seat_ids:
            key = seat_lock_key(show_id, seat_id)
            if redis_client.eval(release_script, 1, key, str(user.id)):
                released_ids.append(seat_id)

    except Exception:
        raise HTTPException(status_code=503,
                            detail='Unable to release seats because the seat-locking service failed')

    for seat_id in released_ids:
        manager.broadcast_sync(show_id,{'type': 'seat_update', 'seat_id': seat_id, 'status': 'Available'})

    return SeatUnlockResponse(message='Your seat locks have been released',
                              show_id=show_id,
                              released_seat_ids=released_ids)