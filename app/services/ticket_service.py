
import hashlib
import hmac
import os
from io import BytesIO

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.config import settings
from reportlab.lib.utils import ImageReader


TICKET_DIR = os.path.abspath('tickets')


def create_ticket_signature(booking_number: str) -> str:
    secret = settings.JWT_SECRET_KEY.encode('utf-8')
    message = booking_number.encode('utf-8')

    return hmac.new(secret,message,hashlib.sha256).hexdigest()


def verify_ticket_signature(booking_number: str,signature: str) -> bool:
    expected = create_ticket_signature(booking_number)
    return hmac.compare_digest(expected, signature)


def generate_ticket_pdf(booking_number: str,event_title: str,venue_name: str,
                        screen_name: str,show_date: str,show_time: str,
                        seats: list[str],amount_paid: str,customer_name: str ) -> str:
   
    os.makedirs(TICKET_DIR, exist_ok=True)

    safe_number = ''.join(char for char in booking_number if char.isalnum() or char in '-_')
    file_path = os.path.join(TICKET_DIR,f"{safe_number}.pdf")

    signature = create_ticket_signature(booking_number)
    qr_value = f"{booking_number}:{signature}"

    qr_image = qrcode.make(qr_value)
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)

    pdf = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    pdf.setTitle(f"Ticket {booking_number}")
    pdf.setFont('Helvetica-Bold', 20)
    pdf.drawString(20 * mm, height - 25 * mm, 'EVENT & MOVIE TICKET')

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(20 * mm, height - 42 * mm, f"Booking: {booking_number}")

    pdf.setFont('Helvetica', 11)
    details = [f"Customer: {customer_name}",
               f"Event / Movie: {event_title}",
               f"Venue: {venue_name}",
               f"Screen: {screen_name}",
               f"Show date: {show_date}",
               f"Show time: {show_time}",
               f"Seats: {', '.join(seats)}",
               f"Seat count: {len(seats)}",
               f"Amount paid: Rs. {amount_paid}"]

    y = height - 55 * mm
    for line in details:
        pdf.drawString(20 * mm, y, line)
        y -= 9 * mm

    pdf.drawImage(ImageReader(qr_buffer),width - 75 * mm,height - 120 * mm,width=48 * mm,height=48 * mm)

    pdf.setFont('Helvetica-Oblique', 9)
    pdf.drawString(20 * mm,20 * mm,'Present this QR code at the entry gate. Each ticket is valid for one entry.')

    pdf.save()
    return file_path


def generate_booking_ticket(db, booking, payment) -> str:
    from app.models.booking import BookingSeat
    from app.models.event import Event, Show
    from app.models.user import User
    from app.models.venue import Screen, Seat, Venue

    show = db.query(Show).filter(Show.id == booking.show_id).first()
    if show is None:
        raise ValueError(f"Show {booking.show_id} was not found for the ticket")

    event = db.query(Event).filter(Event.id == show.event_id).first()
    screen = db.query(Screen).filter(Screen.id == show.screen_id).first()
    customer = db.query(User).filter(User.id == booking.customer_id).first()
    if event is None or screen is None or customer is None:
        raise ValueError(f"Ticket details are incomplete for booking {booking.id}")

    venue = db.query(Venue).filter(Venue.id == screen.venue_id).first()
    if venue is None:
        raise ValueError(f"Venue for booking {booking.id} was not found")

    seats = (db.query(Seat)
            .join(BookingSeat, BookingSeat.seat_id == Seat.id)
            .filter(BookingSeat.booking_id == booking.id)
            .order_by(Seat.row_label, Seat.seat_number)
            .all())

    return generate_ticket_pdf( booking_number=booking.booking_reference,
                                event_title=event.title,
                                venue_name=venue.name,
                                screen_name=screen.name,
                                show_date=str(show.show_date),
                                show_time=str(show.start_time),
                                seats=[f"{seat.row_label}{seat.seat_number}" for seat in seats],
                                amount_paid=str(payment.amount),
                                customer_name=customer.full_name)
