
from pydantic import BaseModel, Field


class TicketScanRequest(BaseModel):
    booking_number: str = Field(min_length=1, max_length=40)
    signature: str = Field(min_length=64, max_length=64)


class TicketScanResponse(BaseModel):
    message: str
    booking_number: str
    customer_name: str
    seats: list[str]
    seat_count: int
    scanned_at: str


class ShowEntriesResponse(BaseModel):
    show_id: int
    confirmed_bookings: int
    entered_bookings: int
    remaining_bookings: int
