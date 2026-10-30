
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (DateTime,ForeignKey,Integer,Numeric,String,UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from sqlalchemy import Boolean


class Booking(Base):
    __tablename__ = 'bookings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_reference: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    show_id: Mapped[int] = mapped_column(ForeignKey('shows.id'), nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='Pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)

    seats = relationship('BookingSeat', back_populates='booking', cascade='all, delete-orphan')
    payments = relationship('Payment', back_populates='booking', cascade='all, delete-orphan')

    seat_count = mapped_column(Integer, nullable=False, default=0)
    ticket_total = mapped_column(Numeric(10, 2), nullable=False, default=0)
    convenience_fee = mapped_column(Numeric(10, 2), nullable=False, default=0)
    gst_amount = mapped_column(Numeric(10, 2), nullable=False, default=0)
    grand_total = mapped_column(Numeric(10, 2), nullable=False, default=0)
    expires_at = mapped_column(DateTime, nullable=True)
    confirmed_at = mapped_column(DateTime, nullable=True)
    reminder_sent = mapped_column(Boolean, nullable=False, default=False)


class BookingSeat(Base):
    __tablename__ = 'booking_seats'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey('bookings.id', ondelete='CASCADE'), nullable=False)
    show_id: Mapped[int] = mapped_column(ForeignKey('shows.id'), nullable=False, index=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey('seats.id'), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    booking = relationship('Booking', back_populates='seats')

    __table_args__ = (
        UniqueConstraint(
            'booking_id', 'seat_id', name='uq_booking_seat'
        ),
    )


class ConfirmedSeat(Base):
    __tablename__ = 'confirmed_seats'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey('bookings.id', ondelete='CASCADE'), nullable=False, index=True
    )
    show_id: Mapped[int] = mapped_column(ForeignKey('shows.id'), nullable=False)
    seat_id: Mapped[int] = mapped_column(ForeignKey('seats.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint('show_id', 'seat_id', name='uq_confirmed_show_seat'),
        UniqueConstraint('booking_id', 'seat_id', name='uq_confirmed_booking_seat'),
    )


class Payment(Base):
    
    __tablename__ = 'payments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column( ForeignKey('bookings.id', ondelete='CASCADE'),nullable=False,index=True )
    payment_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), default='Mock', nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='Pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    booking = relationship('Booking', back_populates='payments')
