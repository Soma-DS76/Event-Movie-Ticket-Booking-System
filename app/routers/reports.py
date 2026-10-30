
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.event import Event, Show
from app.models.venue import Venue, Screen, Seat
from app.models.booking import Booking, BookingSeat
from app.models.refund import Refund
from app.models.ticket import TicketScan


router = APIRouter(prefix='/reports',tags=['Reports & Analytics'])


def apply_event_access(query, user):
    'Limit organizers to their own events.'

    if user.role == 'Admin':
        return query

    if user.role == 'Organizer':
        return query.filter(Event.organizer_id == user.id)

    raise HTTPException(status_code=403,detail='Only Admins and Organizers can access this report')


def date_range(start_date, end_date):
    'Convert inclusive dates to datetime boundaries.'

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422,detail='start_date cannot be after end_date')

    start_dt = (datetime.combine(start_date, time.min)
        if start_date 
        else None )

    end_dt = (datetime.combine(
                end_date + timedelta(days=1),
                time.min)
            if end_date
            else None)

    return start_dt, end_dt


def booking_date_filter(query, start_dt, end_dt):
    'Use confirmation time, falling back to booking creation time.'

    report_time = func.coalesce(Booking.confirmed_at,Booking.created_at)

    if start_dt is not None:
        query = query.filter(report_time >= start_dt)

    if end_dt is not None:
        query = query.filter(report_time < end_dt)

    return query


def confirmed_booking_filter(query):
    return query.filter(Booking.status == 'Confirmed')


def build_sales_subqueries(db, start_dt, end_dt):
    '\n    Calculate ticket counts and booking revenue separately.\n    This prevents revenue from being multiplied by seat joins.\n    '

    # Count booked seats for confirmed bookings.
    ticket_query = (db.query(Booking.show_id.label('show_id'),
                             func.count(BookingSeat.id).label('tickets_sold'))
        .join(BookingSeat,BookingSeat.booking_id == Booking.id))

    ticket_query = confirmed_booking_filter(ticket_query)

    ticket_query = booking_date_filter(ticket_query,start_dt,end_dt)

    ticket_counts = (ticket_query.group_by(Booking.show_id).subquery())

    # Sum each booking total only once.
    revenue_query = db.query(Booking.show_id.label('show_id'),func.sum(Booking.grand_total).label('revenue'))

    revenue_query = confirmed_booking_filter(revenue_query)

    revenue_query = booking_date_filter(revenue_query,start_dt,end_dt)

    sales_totals = (revenue_query.group_by(Booking.show_id).subquery())

    return ticket_counts, sales_totals


# ============================================================
# 1. ADMIN DASHBOARD
# GET /reports/admin-dashboard
# Admin only
# ============================================================

@router.get('/admin-dashboard')
def admin_dashboard(db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    if user.role != 'Admin':
        raise HTTPException(status_code=403,detail='Admin access required')

    today = date.today()

    start_dt = datetime.combine(today, time.min)
    end_dt = start_dt + timedelta(days=1)

    # Today's bookings created.
    today_bookings = (db.query(func.count(Booking.id))
                      .filter(Booking.created_at >= start_dt,Booking.created_at < end_dt).scalar()or 0)

    # Today's confirmed booking revenue.
    revenue_query = db.query(func.coalesce(func.sum(Booking.grand_total),0)).filter(Booking.status == 'Confirmed')

    revenue_query = booking_date_filter(revenue_query,start_dt,end_dt)

    today_revenue = (revenue_query.scalar()or Decimal('0.00'))

    # Today's completed refunds.
    today_refunds = (db.query(func.coalesce(func.sum(Refund.amount),0,))
        .filter(Refund.status == 'Refunded',Refund.refunded_at >= start_dt,Refund.refunded_at < end_dt)
        .scalar()
        or Decimal('0.00'))

    # Published events.
    active_events = (db.query(func.count(Event.id)).filter(Event.status == 'Published').scalar()or 0)

    # Tickets scanned today.
    tickets_scanned = (
        db.query(func.count(TicketScan.id))
        .filter(TicketScan.scanned_at >= start_dt,TicketScan.scanned_at < end_dt).scalar()or 0)

    return {'date': today.isoformat(),
            'today_bookings': today_bookings,
            'today_revenue': float(today_revenue),
            'today_refunds': float(today_refunds),
            'active_events': active_events,
            'tickets_scanned': tickets_scanned}


# ============================================================
# 2. EVENT SALES REPORT
# GET /reports/event-sales
# Admin and Organizer
# ============================================================

@router.get('/event-sales')
def event_sales(start_date: date = Query(...),end_date: date = Query(...),db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    if user.role not in ('Admin', 'Organizer'):
        raise HTTPException(status_code=403,detail='Admin or Organizer access required')

    start_dt, end_dt = date_range(start_date,end_date)

    ticket_counts, sales_totals = build_sales_subqueries(db,start_dt,end_dt,)

    query = (db.query(
            Event.id.label('event_id'),
            Event.title.label('event_title'),
            Show.id.label('show_id'),
            Show.start_time.label('show_start'),
            Venue.name.label('venue_name'),
            func.coalesce(ticket_counts.c.tickets_sold,0,).label('tickets_sold'),
            func.coalesce(sales_totals.c.revenue,0,).label('revenue'))
            .join(Show,Show.event_id == Event.id)
            .join(Screen,Screen.id == Show.screen_id)
            .join(Venue,Venue.id == Screen.venue_id)
            .outerjoin(ticket_counts,ticket_counts.c.show_id == Show.id)
            .outerjoin(sales_totals,sales_totals.c.show_id == Show.id))

    query = apply_event_access(query, user)

    rows = (query.order_by(Show.start_time.desc()).all())

    # Calculate refunds separately by show.
    refund_query = (db.query(Booking.show_id.label('show_id'),
                             func.sum(Refund.amount).label('refund_total'))
                    .join(Booking,Booking.id == Refund.booking_id)
                    .join(Show,Show.id == Booking.show_id)
                    .join(Event,Event.id == Show.event_id)
                    .filter(Refund.status == 'Refunded',
                            Refund.refunded_at >= start_dt,
                            Refund.refunded_at < end_dt))

    if user.role == 'Organizer':
        refund_query = refund_query.filter(Event.organizer_id == user.id)

    refund_rows = (refund_query.group_by(Booking.show_id).all())

    refunds_by_show = {row.show_id: float(row.refund_total or 0)for row in refund_rows}

    return [{'event_id': row.event_id,
            'event_title': row.event_title,
            'show_id': row.show_id,
            'show_start': row.show_start.isoformat(),
            'venue_name': row.venue_name,
            'tickets_sold': row.tickets_sold,
            'revenue': float(row.revenue or 0),
            'refunds': refunds_by_show.get(row.show_id,0.0)}for row in rows]


# ============================================================
# 3. SHOW OCCUPANCY REPORT
# GET /reports/occupancy?show_id=1
# Admin and Organizer
# ============================================================

@router.get('/occupancy')
def show_occupancy(show_id: int = Query(..., gt=0),db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    if user.role not in ('Admin', 'Organizer'):
        raise HTTPException(status_code=403,detail='Admin or Organizer access required')

    show = (db.query(Show)
            .join(Event,Event.id == Show.event_id)
            .filter(Show.id == show_id)
            .first())

    if show is None:
        raise HTTPException(status_code=404,detail='Show not found',)

    if (user.role == 'Organizer'and show.event.organizer_id != user.id):
        raise HTTPException(status_code=403,detail='You do not own this event')

    # Active seats belonging to the show's screen.
    active_seats = (
        db.query(Seat)
        .filter(Seat.screen_id == show.screen_id,Seat.is_active.is_(True))
        .all())

    total_seats = len(active_seats)

    # Unique seats booked by confirmed bookings.
    booked_seat_rows = (
        db.query(BookingSeat.seat_id,Seat.category)
        .join(Booking,Booking.id == BookingSeat.booking_id)
        .join(Seat,Seat.id == BookingSeat.seat_id)
        .filter(Booking.show_id == show_id,
                Booking.status == 'Confirmed',
                Seat.is_active.is_(True)).distinct().all())

    booked_seat_ids = {row.seat_id for row in booked_seat_rows}

    booked_count = len(booked_seat_ids)

    category_totals = {}
    category_booked = {}

    for seat in active_seats:
        category_totals[seat.category] = (category_totals.get(seat.category, 0) + 1)

    for row in booked_seat_rows:
        category_booked[row.category] = (category_booked.get(row.category, 0) + 1)

    categories = {}

    for category, total in category_totals.items():
        booked = category_booked.get(category, 0)

        categories[category] = {'total_seats': total,
                                'booked_seats': booked,
                                'available_seats': total - booked,
                                'occupancy_percentage': (round(booked * 100 / total, 2) if total else 0)}

    return {'show_id': show.id,
            'event_id': show.event_id,
            'event_title': show.event.title,
            'total_seats': total_seats,
            'booked_seats': booked_count,
            'available_seats': total_seats - booked_count,
            'occupancy_percentage': (round(booked_count * 100 / total_seats, 2) if total_seats else 0 ),'categories': categories}


# ============================================================
# 4. TOP 10 EVENTS
# GET /reports/top-events
# Admin only
# ============================================================

@router.get('/top-events')
def top_events( start_date: date = Query(...),
               end_date: date = Query(...),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if user.role != 'Admin':
        raise HTTPException(status_code=403,detail='Admin access required')

    start_dt, end_dt = date_range(start_date,end_date,)

    ticket_counts, sales_totals = build_sales_subqueries(db,start_dt,end_dt)

    # Aggregate ticket counts across all shows for each event.
    event_tickets = (db.query(Show.event_id.label('event_id'),func.sum(ticket_counts.c.tickets_sold).label('tickets_sold'))
                    .join(ticket_counts,ticket_counts.c.show_id == Show.id)
                    .group_by(Show.event_id)
                    .subquery())

    # Aggregate revenue independently to prevent duplication.
    event_revenue = (db.query(Show.event_id.label('event_id'),
                              func.sum(sales_totals.c.revenue).label('revenue'))
                    .join(sales_totals,sales_totals.c.show_id == Show.id)
                    .group_by(Show.event_id)
                    .subquery())

    rows = (db.query(Event.id.label('event_id'),
                     Event.title.label('event_title'),
                     event_tickets.c.tickets_sold,
                    func.coalesce(event_revenue.c.revenue,0).label('revenue'))
        .join(event_tickets,event_tickets.c.event_id == Event.id)
        .outerjoin(event_revenue,event_revenue.c.event_id == Event.id)
        .order_by(event_tickets.c.tickets_sold.desc())
        .limit(10)
        .all())

    return [{'event_id': row.event_id,
            'event_title': row.event_title,
            'tickets_sold': row.tickets_sold or 0,
            'revenue': float(row.revenue or 0)}for row in rows]


# ============================================================
# 5. REFUND REPORT
# GET /reports/refunds
# Admin only
# ============================================================

@router.get('/refunds')
def refund_report(start_date: date = Query(...),
                  end_date: date = Query(...),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
                
    if user.role != 'Admin':
        raise HTTPException(status_code=403,detail='Admin access required')

    start_dt, end_dt = date_range( start_date,end_date)

    rows = (db.query(
            Refund.reason,
            func.count(Refund.id).label('refund_count'),
            func.coalesce(func.sum(Refund.amount),0,).label('amount'))
            .filter(Refund.status == 'Refunded',
                    Refund.refunded_at >= start_dt,
                    Refund.refunded_at < end_dt )
            .group_by(Refund.reason)
            .order_by(Refund.reason)
            .all())

    return {'start_date': start_date.isoformat(),'end_date': end_date.isoformat(),
            'refunds': [{'reason': row.reason,'refund_count': row.refund_count,
                         'amount': float(row.amount or 0)}for row in rows]}
