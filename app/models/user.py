from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(10), nullable=True)

    hashed_password = Column(String(255), nullable=False)

    # Allowed values: Admin, Organizer, Customer, Staff
    role = Column(String(20), nullable=False, default='Customer')

    is_active = Column(Boolean, nullable=False, default=True)
    is_approved = Column(Boolean, nullable=False, default=False)

    # Connected to the Venue model in a later level
    venue_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column( DateTime,nullable=False,default=datetime.utcnow,onupdate=datetime.utcnow)