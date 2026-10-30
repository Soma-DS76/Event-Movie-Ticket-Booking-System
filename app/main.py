
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from app.routers import (auth,admin,venues,events,seat_locking,websocket,
                         bookings,payments,tickets,cancellations,waitlist,reports)

from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers.websocket import listen_for_lock_expirations
from app.utils.error_handlers import (http_exception_handler,validation_exception_handler,database_exception_handler)


# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    expiry_listener = asyncio.create_task(listen_for_lock_expirations())

    try:
        yield
    finally:
        expiry_listener.cancel()
        try:
            await expiry_listener
        except asyncio.CancelledError:
            pass
        stop_scheduler()


# Create FastAPI application
app = FastAPI(title='Event & Movie Ticket Booking System',lifespan=lifespan)


# Register exception handlers
app.add_exception_handler(HTTPException,http_exception_handler)
app.add_exception_handler(RequestValidationError,validation_exception_handler)
app.add_exception_handler(SQLAlchemyError,database_exception_handler )


# Register routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(seat_locking.router)
app.include_router(websocket.router)
app.include_router(bookings.router)
app.include_router(payments.router)
app.include_router(tickets.router)
app.include_router(cancellations.router)
app.include_router(waitlist.router)
app.include_router(reports.router)

# Root endpoint
@app.get('/')
def root():
    return {'message': 'Event & Movie Ticket Booking System API'}


@app.get('/seat-map-test', include_in_schema=False)
def seat_map_test():
    page = Path(__file__).resolve().parent.parent / 'static' / 'seat_map_test.html'
    return FileResponse(page, media_type='text/html')
