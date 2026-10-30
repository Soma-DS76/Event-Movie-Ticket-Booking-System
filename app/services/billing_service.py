
from decimal import Decimal, ROUND_HALF_UP


CONVENIENCE_FEE_PER_SEAT = Decimal('30.00')
GST_RATE = Decimal('0.18')


def calculate_booking_bill(seat_prices: list):

    ticket_total = sum((Decimal(str(price)) for price in seat_prices),Decimal('0.00'))

    seat_count = len(seat_prices)

    convenience_fee = CONVENIENCE_FEE_PER_SEAT * seat_count

    gst_amount = ((ticket_total + convenience_fee) * GST_RATE).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

    grand_total = (ticket_total + convenience_fee + gst_amount).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

    return {'seat_count': seat_count,'ticket_total': ticket_total,'convenience_fee': convenience_fee,
            'gst_amount': gst_amount,'grand_total': grand_total}
