
from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    payment_method: Literal['UPI', 'Card', 'Net Banking']
    simulate_status: Literal['Success', 'Failed']


class PaymentResponse(BaseModel):
    id: int
    booking_id: int
    transaction_id: str = Field(validation_alias='payment_reference')
    amount: Decimal
    payment_method: str
    status: str
    paid_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
