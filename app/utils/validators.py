import re
from datetime import datetime, date

from fastapi import HTTPException


def validate_phone(phone):
    if phone is None:
        return None

    if not re.fullmatch('[0-9]{10}', phone):
        raise HTTPException(status_code=422,detail='Phone number must contain exactly 10 digits')

    return phone


def validate_seat_price(price):
    if price <= 0:
        raise HTTPException(status_code=422,detail='Seat price must be greater than zero')

    return price


def validate_duration(duration):
    if duration < 30 or duration > 300:
        raise HTTPException(status_code=422,detail='Event duration must be between 30 and 300 minutes')

    return duration


def validate_show_date(show_date):
    if isinstance(show_date, datetime):
        if show_date <= datetime.now():
            raise HTTPException(status_code=422,detail='Show must start in the future')

    elif isinstance(show_date, date):
        if show_date < date.today():
            raise HTTPException(status_code=422,detail='Show date cannot be in the past')

    return show_date