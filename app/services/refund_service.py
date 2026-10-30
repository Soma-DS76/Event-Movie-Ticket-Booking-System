
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


def calculate_customer_refund(ticket_total: Decimal,show_start: datetime ) -> Decimal:

    remaining = show_start - datetime.now()

    if remaining < timedelta(hours=2):
        raise ValueError('Cancellation is not allowed less than 2 hours before the show')

    if remaining > timedelta(hours=24):
        percentage = Decimal('1.00')
    else:
        percentage = Decimal('0.50')

    return (ticket_total * percentage).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
