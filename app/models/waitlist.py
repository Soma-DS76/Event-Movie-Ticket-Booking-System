
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Waitlist(Base):
    __tablename__ = 'waitlists'

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey('shows.id'), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    seat_count = Column(Integer, nullable=False)
    preferred_category = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('show_id', 'customer_id', name='uq_waitlist_show_customer'),
    )

    show = relationship('Show')
    customer = relationship('User')
