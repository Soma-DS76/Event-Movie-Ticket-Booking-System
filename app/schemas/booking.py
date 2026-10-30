
from datetime import datetime
from decimal import Decimal
from typing import Optional
from typing import List

from pydantic import BaseModel, Field, ConfigDict


class BookingCreate(BaseModel):
    show_id: int = Field(gt=0)
    seat_ids: List[int] = Field(min_length=1, max_length=10)


class BookingSeatResponse(BaseModel):
    seat_id: int
    price: Decimal

    model_config = ConfigDict(from_attributes=True)


class BookingResponse(BaseModel):
    id: int
    booking_reference: str
    show_id: int
    seat_count: int
    ticket_total: Decimal
    convenience_fee: Decimal
    gst_amount: Decimal
    grand_total: Decimal
    total_amount: Decimal
    status: str
    expires_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    seats: List[BookingSeatResponse]

    model_config = ConfigDict(from_attributes=True)
