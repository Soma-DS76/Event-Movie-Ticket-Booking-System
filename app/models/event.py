
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (Column, Integer, String, Text, Date, DateTime,Numeric, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, index=True)
    organizer_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    category = Column(String(30), nullable=False)
    language = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    age_rating = Column(String(5), nullable=False)
    status = Column(String(20), nullable=False, default='Draft')

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,onupdate=datetime.utcnow, nullable=False)

    organizer = relationship('User')
    shows = relationship('Show', back_populates='event')


class Show(Base):
    __tablename__ = 'shows'

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False, index=True)
    screen_id = Column(Integer, ForeignKey('screens.id'), nullable=False, index=True)
    show_date = Column(Date, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    booking_closes_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default='Scheduled')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,onupdate=datetime.utcnow, nullable=False)
    event = relationship('Event', back_populates='shows')
    screen = relationship('Screen')
    prices = relationship('SeatCategoryPrice',back_populates='show',cascade='all, delete-orphan')



class SeatCategoryPrice(Base):
    __tablename__ = 'seat_category_prices'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    show_id: Mapped[int] = mapped_column(ForeignKey('shows.id'),nullable=False,index=True)

    category: Mapped[str] = mapped_column(String(30),nullable=False)

    price: Mapped[Decimal] = mapped_column(Numeric(10, 2),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            'show_id',
            'category',
            name='uq_show_category'
        ),
    )

    show = relationship('Show',back_populates='prices')
