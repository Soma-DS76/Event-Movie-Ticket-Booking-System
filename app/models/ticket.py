
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TicketScan(Base):
    __tablename__ = 'ticket_scans'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey('bookings.id'),
                                            nullable=False,unique=True,index=True)
    staff_id: Mapped[int] = mapped_column( ForeignKey('users.id'),nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
