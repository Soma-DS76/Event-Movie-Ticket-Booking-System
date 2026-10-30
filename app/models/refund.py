
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class Refund(Base):
    __tablename__ = 'refunds'

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reason = Column(String(50), nullable=False)
    status = Column(String(20), default='Refunded', nullable=False)
    refunded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    booking = relationship('Booking')
    payment = relationship('Payment')
