# Event & Movie Ticket Booking System

FastAPI backend for organizer-managed events and shows, live seat booking, Redis seat locks, mock payments, QR/PDF tickets, entry scanning, cancellations/refunds, waitlists, scheduled jobs, and reports.


## Stack

- Python 3.9+
- FastAPI, Pydantic, SQLAlchemy, MySQL, Alembic
- Redis for seat locks, cache, and rate limiting
- JWT authentication and role-based access control
- WebSockets for live seat-map updates
- APScheduler and SMTP email notifications
- qrcode and ReportLab for signed QR-code PDF tickets


## 📁 Project Structure

```text
Event-Movie-Ticket-Booking-System/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── venue.py
│   │   ├── event.py
│   │   ├── show.py
│   │   ├── booking.py
│   │   ├── payment.py
│   │   ├── waitlist.py
│   │   ├── refund.py
│   │   └── ticket_scan.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── venue.py
│   │   ├── event.py
│   │   ├── show.py
│   │   ├── booking.py
│   │   ├── payment.py
│   │   └── ticket.py
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── venues.py
│   │   ├── events.py
│   │   ├── shows.py
│   │   ├── bookings.py
│   │   ├── payments.py
│   │   ├── cancellations.py
│   │   ├── tickets.py
│   │   ├── waitlist.py
│   │   └── reports.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── booking_service.py
│   │   ├── payment_service.py
│   │   ├── ticket_service.py
│   │   ├── email_service.py
│   │   └── refund_service.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── security.py
│   │   ├── cache.py
│   │   ├── redis_client.py
│   │   └── validators.py
│   │
│   └── jobs/
│       ├── __init__.py
│       └── scheduler.py
│
├── alembic/
│   ├── versions/
│   │   └── [database migration files]
│   ├── env.py
│   └── script.py.mako
│
├── tickets/
│   └── [generated ticket PDFs]
│
├── logs/
│   └── [application logs]
│
├── alembic.ini
├── requirements.txt
├── ScreenShots
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── README.md
```


## Local setup (Windows CMD)

1. Install Python 3.9+, MySQL 8+, and Redis.
2. Open CMD in the project folder.
3. Create and activate the environment:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Create the local configuration file:

   ```bat
   copy .env.example .env
   ```

5. Edit `.env` and set your MySQL password, Redis URL, and a random JWT secret. Keep `.env` private; it is ignored by Git and is not included in this ZIP.
6. Create the `event_booking_db` MySQL database if it does not exist.
7. Run migrations and start the server:

   ```bat
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

8. Open `http://127.0.0.1:8000/docs` for API documentation.

## Docker setup

Docker Compose starts MySQL, Redis, and the API. Before running it, create `.env` from `.env.example` and set these container-network values:

```dotenv
DATABASE_URL=mysql+pymysql://root:change_this_password@mysql:3306/event_booking_db
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=replace_with_a_random_secret_at_least_32_characters_long
```

Set `MYSQL_ROOT_PASSWORD` in your shell to the same MySQL password, then run:

```bash
docker compose up --build
```

The API runs at `http://localhost:8000`.

## Main booking flow

1. Register and log in. Use the returned access token as a Bearer token.
2. Lock seats using `POST /shows/{show_id}/lock-seats`.
3. Create a booking using `POST /bookings` for the seats locked by the same customer.
4. Pay using `POST /bookings/{booking_id}/pay`; `simulate_status` is `Success` or `Failed` for mock-payment outcomes.
5. Download the PDF ticket using `GET /bookings/{booking_id}/ticket` after successful payment.

## Live seat map

Open `http://localhost:8000/seat-map-test`, enter a show ID and access token, then connect. Alternatively, use:

```text
ws://localhost:8000/ws/shows/1/seats?token=<access_token>
```

The WebSocket sends the current map first and then broadcasts seat-state updates.

## Migrations

All schema changes are managed by Alembic. Do not use SQLAlchemy `create_all()` to create tables. The added migration `f39a7b2c1d80` aligns the ticket-scan booking index with the model's unique index.

## Code style and security

Python formatting is configured in `.ruff.toml` to use single quotes. Do not commit `.env`, generated PDFs, virtual environments, caches, or credentials. Generated ticket files are stored in `tickets/`, which is ignored by Git.

## Important note

This is a development project with mock payments, not a production payment service. Configure valid infrastructure and SMTP credentials before relying on emails or scheduled processing. Review and run your full acceptance/API test suite against a dedicated test database before deployment.
