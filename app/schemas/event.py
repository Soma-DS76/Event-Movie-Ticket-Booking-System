
from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict

from pydantic import Field
from typing import Optional


EventCategory = Literal['Movie', 'Concert', 'Comedy', 'Sports', 'Workshop']
AgeRating = Literal['U', 'UA', 'A']
EventStatus = Literal['Draft', 'Published', 'Cancelled']
SeatCategory = Literal['Silver', 'Gold', 'Recliner']


class EventCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    category: EventCategory
    language: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    age_rating: AgeRating
    status: EventStatus = 'Draft'
    duration_minutes: int = Field(ge=30,le=300)


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    category: Optional[EventCategory] = None
    language: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    age_rating: Optional[AgeRating] = None
    status: Optional[EventStatus] = None
    dduration_minutes: Optional[int] = Field(default=None,ge=30,le=300)


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organizer_id: int
    title: str
    category: str
    language: str
    description: Optional[str]
    duration_minutes: int
    age_rating: str
    status: str


class CategoryPriceCreate(BaseModel):
    category: SeatCategory
    price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)


class ShowCreate(BaseModel):
    screen_id: int
    show_date: date
    start_time: time
    prices: List[CategoryPriceCreate] = Field(..., min_length=1)


class ShowUpdate(BaseModel):
    screen_id: Optional[int] = None
    show_date: Optional[date] = None
    start_time: Optional[time] = None
    prices: Optional[List[CategoryPriceCreate]] = None


class CategoryPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    price: Decimal


class ShowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    screen_id: int
    show_date: date
    start_time: datetime
    end_time: datetime
    booking_closes_at: datetime
    status: str
    prices: List[CategoryPriceResponse]
