
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.config import settings


logger = logging.getLogger(__name__)


def send_email(to_email: str,subject: str,body: str,attachment_path: Optional[str] = None) -> bool:

    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.warning('SMTP credentials are not configured')
        return False

    message = EmailMessage()
    message['From'] = settings.SMTP_USERNAME
    message['To'] = to_email
    message['Subject'] = subject
    message.set_content(body)

    if attachment_path:
        if not os.path.isfile(attachment_path):
            logger.error('Email attachment not found: %s', attachment_path)
            return False

        with open(attachment_path, 'rb') as file:
            message.add_attachment(file.read(),maintype='application',
                                   subtype='pdf', filename=os.path.basename(attachment_path))

    try:
        with smtplib.SMTP(settings.SMTP_HOST,settings.SMTP_PORT,timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USERNAME,settings.SMTP_PASSWORD)
            smtp.send_message(message)

        logger.info('Email sent to %s', to_email)
        return True

    except (smtplib.SMTPException, OSError) as exc:
        logger.error('Email sending failed: %s', exc)
        return False


def send_booking_confirmation(to_email: str,customer_name: str,booking_reference: str,event_title: str,amount_paid: str,ticket_path: str) -> bool:

    subject = f"Booking Confirmed - {booking_reference}"

    body = f"""Hello {customer_name},

        Your booking has been confirmed successfully!

        Booking Reference: {booking_reference}
        Event / Movie: {event_title}
        Amount Paid: Rs. {amount_paid}

        Your ticket PDF is attached to this email.

        Please present the QR code at the entry gate.

        Thank you for booking with us!
        Event & Movie Ticket Booking System
        """

    return send_email(to_email,subject,body,attachment_path=ticket_path)


def send_payment_failed(to_email: str,booking_reference: str) -> bool:

    return send_email(to_email,
                      'Payment Failed',
                      f"""Your payment for booking {booking_reference} failed.
                      You can retry payment while your seat lock is active.""")


def send_booking_cancelled(to_email: str,booking_reference: str,refund_amount: str) -> bool:

    return send_email(
        to_email,
        f"Booking Cancelled - {booking_reference}",
        f"""Your booking {booking_reference} has been cancelled.

Refund Amount: Rs. {refund_amount}

Any applicable refund will be processed according to the refund policy.""" )


def send_show_cancelled(to_email: str,event_title: str,booking_reference: str,
                        refund_amount: Optional[str] = None) -> bool:
    refund_details = (f"\nFull refund amount: Rs. {refund_amount}" if refund_amount is not None else '')

    return send_email(to_email,
        'Show Cancelled',
        f"""The following show has been cancelled:

        Event / Movie: {event_title}
        Booking Reference: {booking_reference}
        Your booking has been cancelled and a full mock refund has been recorded.
        {refund_details}""")


def send_waitlist_notification(to_email: str,event_title: str,show_id: int) -> bool:

    return send_email(to_email,'Seats May Be Available', f"""Seats may now be available for:

                      Event / Movie: {event_title}
                      Show ID: {show_id}

                      Please check availability and book your seats.""")


def send_show_reminder(to_email: str,event_title: str,show_date: str,show_time: str) -> bool:

    return send_email( to_email,'Upcoming Show Reminder',
                       f"""This is a reminder about your upcoming show.

                        Event / Movie: {event_title}
                        Date: {show_date}
                        Time: {show_time}

                        Please arrive at the venue on time and carry your ticket QR code.""")
