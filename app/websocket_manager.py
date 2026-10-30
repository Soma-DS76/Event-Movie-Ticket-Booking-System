
import asyncio
import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, dict[WebSocket, int]] = {}
        self.loop = None

    async def connect(self, show_id: int, websocket: WebSocket, user_id: int):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.setdefault(show_id, {})[websocket] = user_id

    def disconnect(self, show_id: int, websocket: WebSocket):
        connections = self.active_connections.get(show_id, {})
        connections.pop(websocket, None)

        if not connections:
            self.active_connections.pop(show_id, None)

    async def broadcast(self, show_id: int, message: dict):
        connections = list(self.active_connections.get(show_id, {}).items())

        for websocket, user_id in connections:
            outgoing = dict(message)
            owner_id = outgoing.pop('_owner_id', None)
            if outgoing.get('status') == 'Locked' and owner_id == user_id:
                outgoing['status'] = 'Yours'
            try:
                await websocket.send_json(outgoing)
            except WebSocketDisconnect:
                self.disconnect(show_id, websocket)
            except Exception:
                logger.exception('Could not send seat update to WebSocket client')
                self.disconnect(show_id, websocket)

    def broadcast_sync(self, show_id: int, message: dict):
        if self.loop is None or not self.loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(show_id, message), self.loop)


manager = ConnectionManager()
