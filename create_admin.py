from getpass import getpass

from app.database import SessionLocal
from app.models.user import User
from app.auth.security import hash_password


def main():
    db = SessionLocal()

    try:
        full_name = input('Admin full name: ').strip()
        email = input('Admin email: ').strip().lower()
        password = getpass('Admin password (minimum 8 characters): ')

        if len(password) < 8:
            print('Password must contain at least 8 characters.')
            return

        existing = db.query(User).filter(User.email == email).first()

        if existing:
            print('An account with this email already exists.')
            return

        admin = User(full_name=full_name,email=email,hashed_password=hash_password(password),
                     role='Admin',is_active=True,is_approved=True )

        db.add(admin)
        db.commit()

        print('Admin account created successfully.')

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()