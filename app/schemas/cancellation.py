
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RefundResponse(BaseModel):
    id: int
    booking_id: int
    amount: Decimal
    reason: str
    status: str
    refunded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CancellationResponse(BaseModel):
    message: str
    booking_id: int
    booking_status: str
    refund_amount: Decimal


class WaitlistCreate(BaseModel):
    seat_count: int = Field(ge=1, le=10)
    preferred_category: str = Field(min_length=1, max_length=50)


class WaitlistResponse(BaseModel):
    id: int
    show_id: int
    customer_id: int
    seat_count: int
    preferred_category: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
