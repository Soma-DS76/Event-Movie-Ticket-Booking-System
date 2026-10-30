import logging

from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'success': False,
            'message': exc.detail,
        },
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = []

    for error in exc.errors():
        errors.append({
            'field': '.'.join(map(str, error['loc'])),
            'message': str(error['msg']),
        })

    return JSONResponse(
        status_code=422,
        content={
            'success': False,
            'message': 'Validation failed',
            'errors': errors,
        },
    )


async def database_exception_handler(request: Request,exc: SQLAlchemyError):
    logger.error('Database error on %s',request.url.path,exc_info=True )

    return JSONResponse(status_code=500,content={'success': False,'message': 'Database operation failed' })