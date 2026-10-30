from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import StaffCreate, UserResponse
from app.auth.dependencies import require_roles
from app.auth.security import hash_password

router = APIRouter(prefix='/admin', tags=['Admin'])

admin_only = require_roles('Admin')


@router.put('/organizers/{user_id}/approve',response_model=UserResponse)
def approve_organizer(user_id: int,db: Session = Depends(get_db),admin: User = Depends(admin_only)):
    organizer = db.query(User).filter(User.id == user_id).first()

    if organizer is None:
        raise HTTPException(status_code=404, detail='User not found')

    if organizer.role != 'Organizer':
        raise HTTPException(status_code=400,detail='This user is not an Organizer')

    organizer.is_approved = True
    db.commit()
    db.refresh(organizer)

    return organizer


@router.post('/staff',response_model=UserResponse,status_code=status.HTTP_201_CREATED)
def create_staff(data: StaffCreate,db: Session = Depends(get_db),admin: User = Depends(admin_only)):
    email = str(data.email).lower()

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409,detail='An account with this email already exists')

    staff = User(full_name=data.full_name.strip(),email=email,phone=data.phone,
                 hashed_password=hash_password(data.password),role='Staff',
                 is_active=True,is_approved=True,venue_id=data.venue_id)

    db.add(staff)
    db.commit()
    db.refresh(staff)

    return staff