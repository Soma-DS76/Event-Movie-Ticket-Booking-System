import asyncio
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.security import decode_access_token
from app.database import SessionLocal
from app.models.user import User
from app.redis_client import redis_client
from app.services.seat_map_service import build_seat_map
from app.websocket_manager import manager


logger = logging.getLogger(__name__)
router = APIRouter(tags=['Live Seat Map'])
LOCK_KEY_PATTERN = re.compile('^lock:show:(\\d+):seat:(\\d+)$')


@router.websocket('/ws/shows/{show_id}/seats')
async def live_seat_map(websocket: WebSocket, show_id: int):
    token = websocket.query_params.get('token')
    payload = decode_access_token(token) if token else None
    try:
        user_id = int(payload['sub']) if payload else 0
    except (KeyError, TypeError, ValueError):
        user_id = 0

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        if user is None or not user.is_active or user.role != 'Customer':
            await websocket.close(code=1008, reason='Invalid access token')
            return

        try:
            seats = build_seat_map(db, show_id, user.id)
        except Exception:
            await websocket.close(code=1008, reason='Show is unavailable')
            return

        await manager.connect(show_id, websocket, user.id)
        await websocket.send_json({'type': 'seat_map',
                                   'show_id': show_id,
                                   'seats': [seat.model_dump(mode='json') for seat in seats]})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(show_id, websocket)
    finally:
        db.close()
        manager.disconnect(show_id, websocket)


async def listen_for_lock_expirations():
    pubsub = None
    try:
        current = await asyncio.to_thread(redis_client.config_get, 'notify-keyspace-events')
        flags = current.get('notify-keyspace-events', '')
        if 'A' not in flags:
            await asyncio.to_thread(redis_client.config_set,
                                    'notify-keyspace-events',
                                    flags + 'Ex' )
        pubsub = redis_client.pubsub()
        await asyncio.to_thread(pubsub.psubscribe, '__keyevent@*__:expired')

        while True:
            message = await asyncio.to_thread(pubsub.get_message, True, 1.0)
            if not message or message.get('type') != 'pmessage':
                continue
            key = message.get('data')
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            match = LOCK_KEY_PATTERN.match(str(key))
            if match:
                show_id, seat_id = map(int, match.groups())
                await manager.broadcast(show_id,{'type': 'seat_update',
                                                'seat_id': seat_id,
                                                'status': 'Available'})
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception('Redis seat-lock expiry notifications are unavailable')
    finally:
        if pubsub is not None:
            await asyncio.to_thread(pubsub.close)
