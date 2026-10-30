from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SeatLockRequest(BaseModel):
    seat_ids: List[int] = Field(min_length=1, max_length=10)


class SeatMapItem(BaseModel):
    seat_id: int
    row_label: str
    seat_number: int
    category: str
    price: float
    status: str


class SeatMapResponse(BaseModel):
    show_id: int
    seats: List[SeatMapItem]


class SeatLockResponse(BaseModel):
    message: str
    show_id: int
    seat_ids: List[int]
    expires_in_seconds: int
    expires_at: Optional[datetime] = None


class SeatUnlockResponse(BaseModel):
    message: str
    show_id: int
    released_seat_ids: List[int]