from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.models.event import Event, Show
from app.models.venue import Seat
from app.models.waitlist import Waitlist
from app.services.email_service import send_waitlist_notification


def notify_waitlisted_customers(
    db: Session,
    show_id: int,
    released_seat_ids: list[int],
    background_tasks: BackgroundTasks,
) -> None:
    if not released_seat_ids:
        return

    show = db.query(Show).filter(Show.id == show_id).first()
    event = db.query(Event).filter(Event.id == show.event_id).first() if show else None
    if show is None or event is None:
        return

    released_seats = (
        db.query(Seat)
        .filter(Seat.id.in_(released_seat_ids), Seat.is_active.is_(True))
        .all()
    )
    available_by_category: dict[str, int] = {}
    for seat in released_seats:
        available_by_category[seat.category] = (
            available_by_category.get(seat.category, 0) + 1
        )

    entries = (
        db.query(Waitlist)
        .filter(Waitlist.show_id == show_id)
        .order_by(Waitlist.created_at, Waitlist.id)
        .all()
    )
    for entry in entries:
        available = available_by_category.get(entry.preferred_category, 0)
        if available < entry.seat_count:
            continue
        background_tasks.add_task(
            send_waitlist_notification,
            entry.customer.email,
            event.title,
            show_id,
        )
        available_by_category[entry.preferred_category] = available - entry.seat_count
