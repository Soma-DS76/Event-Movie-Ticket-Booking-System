import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

from app.database import SessionLocal
from app.models.booking import Booking
from app.models.event import Event, Show
from app.models.user import User
from app.services.email_service import (send_show_reminder)


logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone='Asia/Kolkata')


def expire_pending_bookings():
    db = SessionLocal()

    try:
        now = datetime.now()

        bookings = (db.query(Booking)
                    .filter(Booking.status.in_(['Pending', 'Pending Payment']),
                            Booking.expires_at.isnot(None),
                            Booking.expires_at <= now ).all())

        for booking in bookings:
            booking.status = 'Expired'

        db.commit()

    except Exception:
        db.rollback()
        logger.exception('Booking expiry job failed')

    finally:
        db.close()


def send_show_reminders():
    db = SessionLocal()

    try:
        now = datetime.now()
        deadline = now + timedelta(hours=3)

        bookings = (
            db.query(Booking, Show, User)
            .join(Show, Booking.show_id == Show.id)
            .join(User, Booking.customer_id == User.id)
            .filter(Booking.status == 'Confirmed',
                    Booking.reminder_sent.is_(False),
                    Show.status == 'Scheduled',
                    Show.start_time > now,
                    Show.start_time <= deadline ).all())

        for booking, show, user in bookings:
            # Mark before scheduling so repeated job runs
            # do not send duplicate reminders.
            booking.reminder_sent = True

        db.commit()

        for booking, show, user in bookings:
            send_show_reminder(user.email,
                               show.event.title,
                               str(show.show_date),
                               show.start_time.strftime('%H:%M'))

    except Exception:
        db.rollback()
        logger.exception('Show reminder job failed')

    finally:
        db.close()


def complete_shows():
    db = SessionLocal()

    try:
        now = datetime.now()

        shows = (db.query(Show)
                 .filter(Show.status == 'Scheduled',Show.end_time <= now).all())

        for show in shows:
            show.status = 'Completed'

        db.commit()

    except Exception:
        db.rollback()
        logger.exception('Show completion job failed')

    finally:
        db.close()


def complete_events():
    db = SessionLocal()

    try:
        events = (db.query(Event)
                  .filter(Event.status != 'Completed').all())

        for event in events:
            total = (db.query(func.count(Show.id))
                     .filter(Show.event_id == event.id)
                     .scalar())

            completed = (db.query(func.count(Show.id))
                         .filter(Show.event_id == event.id,Show.status == 'Completed')
                         .scalar())

            if total > 0 and total == completed:
                event.status = 'Completed'

        db.commit()

    except Exception:
        db.rollback()
        logger.exception('Event completion job failed')

    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(expire_pending_bookings,
                      'interval',
                      minutes=1,
                      id='expire_bookings',
                      replace_existing=True,
                      max_instances=1,
                      coalesce=True)

    scheduler.add_job(send_show_reminders,
                      'interval',
                      minutes=30,
                      id='show_reminders',
                      replace_existing=True,
                      max_instances=1,
                      coalesce=True)

    scheduler.add_job(complete_shows,
                      'interval',
                      minutes=15,
                      id='complete_shows',
                      replace_existing=True,
                      max_instances=1,
                      coalesce=True)

    scheduler.add_job(  complete_events,
                        'cron',
                        hour=1,
                        minute=0,
                        id='complete_events',
                        replace_existing=True,
                        max_instances=1,
                        coalesce=True)

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)