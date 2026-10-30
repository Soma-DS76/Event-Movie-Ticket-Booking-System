from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, UserResponse, TokenResponse
from app.auth.security import ( hash_password,verify_password, create_access_token)
from app.auth.dependencies import get_current_user

from fastapi import Request
from app.utils.rate_limit import check_rate_limit

router = APIRouter(prefix='/auth', tags=['Authentication'])


@router.post('/register',response_model=UserResponse,status_code=status.HTTP_201_CREATED )
def register_user(data: UserRegister, db: Session = Depends(get_db)):
    email = str(data.email).lower()

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409,detail='An account with this email already exists' )

    user = User(full_name=data.full_name.strip(),email=email,
                phone=data.phone,hashed_password=hash_password(data.password),
                role=data.role,is_active=True,is_approved=(data.role == 'Customer'))

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post('/login', response_model=TokenResponse)
def login(data: UserLogin, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else 'unknown'
    try:
        check_rate_limit(f"rate:login:{client_ip}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail='Rate-limiting service is temporarily unavailable'
        ) from exc

    email = str(data.email).lower()

    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Incorrect email or password',
                            headers={'WWW-Authenticate': 'Bearer'})

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='This account is inactive')

    token = create_access_token(user_id=user.id, role=user.role)

    return {'access_token': token,'token_type': 'bearer','expires_in_minutes': 30,
            'user': user }


@router.get('/me', response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user