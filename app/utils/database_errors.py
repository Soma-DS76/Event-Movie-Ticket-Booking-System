from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


def commit_or_conflict(db, message='Duplicate record'):
    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(status_code=409,detail=message)