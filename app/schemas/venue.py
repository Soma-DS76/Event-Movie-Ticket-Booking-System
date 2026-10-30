
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


SeatCategory = Literal['Silver', 'Gold', 'Recliner']


class VenueCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    city: str = Field(..., min_length=2, max_length=100)
    address: str = Field(..., min_length=3, max_length=500)
    is_active: bool = True


class VenueUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    address: Optional[str] = Field(default=None, min_length=3, max_length=500)
    is_active: Optional[bool] = None


class VenueResponse(BaseModel):
    id: int
    name: str
    city: str
    address: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ScreenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ScreenResponse(BaseModel):
    id: int
    venue_id: int
    name: str
    total_seats: int

    model_config = ConfigDict(from_attributes=True)


class SeatRowCreate(BaseModel):
    row_label: str = Field(..., min_length=1, max_length=10)
    seat_count: int = Field(..., gt=0, le=100)
    category: SeatCategory


class BulkSeatCreate(BaseModel):
    rows: List[SeatRowCreate] = Field(..., min_length=1)


class SeatResponse(BaseModel):
    id: int
    screen_id: int
    row_label: str
    seat_number: int
    category: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SeatRowLayout(BaseModel):
    row_label: str
    seats: List[SeatResponse]


class ScreenLayoutResponse(BaseModel):
    screen_id: int
    screen_name: str
    venue_id: int
    total_seats: int
    rows: List[SeatRowLayout]


class SeatStatusUpdate(BaseModel):
    is_active: bool
