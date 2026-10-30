from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from pydantic import field_validator
import re

class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone: Optional[str] = Field( default=None,pattern='^[0-9]{10}$')
    role: Literal['Customer', 'Organizer'] = 'Customer'


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str]
    role: str
    is_active: bool
    is_approved: bool
    venue_id: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in_minutes: int = 30
    user: UserResponse


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone: str = Field(pattern='^[0-9]{10}$')
    venue_id: int = Field(gt=0)

@field_validator('phone')
@classmethod
def check_phone(cls, value):
    if value is not None:
        if not re.fullmatch('[0-9]{10}', value):
            raise ValueError('Phone number must contain exactly 10 digits')

    return value