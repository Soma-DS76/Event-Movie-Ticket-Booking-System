
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Venue(Base):
    __tablename__ = 'venues'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    address = Column(String(500), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    screens = relationship(
        'Screen',
        back_populates='venue',
        cascade='all, delete-orphan',
    )


class Screen(Base):
    __tablename__ = 'screens'

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(
        Integer,
        ForeignKey('venues.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    total_seats = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    venue = relationship('Venue', back_populates='screens')
    seats = relationship(
        'Seat',
        back_populates='screen',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        UniqueConstraint(
            'venue_id',
            'name',
            name='uq_screen_venue_name',
        ),
    )


class Seat(Base):
    __tablename__ = 'seats'

    id = Column(Integer, primary_key=True, index=True)
    screen_id = Column(
        Integer,
        ForeignKey('screens.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    row_label = Column(String(10), nullable=False)
    seat_number = Column(Integer, nullable=False)
    category = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    screen = relationship('Screen', back_populates='seats')

    __table_args__ = (
        UniqueConstraint(
            'screen_id',
            'row_label',
            'seat_number',
            name='uq_seat_screen_row_number',
        ),
    )
