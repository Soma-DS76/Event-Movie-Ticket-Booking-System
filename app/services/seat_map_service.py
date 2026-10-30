import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.booking import ConfirmedSeat
from app.models.event import Show
from app.models.venue import Seat
from app.redis_client import redis_client
from app.schemas.seat_lock import SeatMapItem


logger = logging.getLogger(__name__)


def build_seat_map(db: Session, show_id: int, user_id: int) -> list[SeatMapItem]:
    show = db.query(Show).filter(Show.id == show_id).first()
    if show is None:
        raise HTTPException(status_code=404, detail='Show not found')

    try:
        locked = {}
        for key in redis_client.scan_iter(match=f"lock:show:{show_id}:seat:*", count=100):
            value = redis_client.get(key)
            if value is not None:
                locked[int(key.rsplit(':', 1)[1])] = value
    except Exception as exc:
        logger.exception('Unable to load locks for show %s', show_id)
        raise HTTPException(status_code=503,detail='Seat-locking service is temporarily unavailable') from exc

    prices = {price.category: price.price for price in show.prices}
    booked_ids = {row[0] for row in db.query(ConfirmedSeat.seat_id) .filter(ConfirmedSeat.show_id == show_id).all()}

    result = []
    seats = (db.query(Seat)
            .filter(Seat.screen_id == show.screen_id)
            .order_by(Seat.row_label, Seat.seat_number)
            .all())
    for seat in seats:
        if not seat.is_active:
            status = 'Unavailable'
        elif seat.id in booked_ids:
            status = 'Booked'
        elif seat.id in locked:
            status = 'Yours' if locked[seat.id] == str(user_id) else 'Locked'
        else:
            status = 'Available'
        result.append(
            SeatMapItem(seat_id=seat.id,
                        row_label=seat.row_label,
                        seat_number=seat.seat_number,
                        category=seat.category,
                        price=float(prices.get(seat.category, 0)),
                        status=status))
    return result
