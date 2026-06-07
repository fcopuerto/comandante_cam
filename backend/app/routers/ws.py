"""
WebSocket hub — real-time updates for camera status, alerts, and export progress.
Auth via ?token=<access_token> query param (browsers can't set headers on WS).
"""
import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import decode_access_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["websocket"])

_MAX_CONNECTIONS_PER_USER = 5
_PING_INTERVAL = 30.0
_PONG_TIMEOUT = 10.0


class ConnectionManager:
    def __init__(self) -> None:
        # user_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        # reverse map: WebSocket → user_id
        self._ws_to_user: dict[WebSocket, str] = {}
        # WebSocket → set of camera_ids this client is viewing
        self._ws_cameras: dict[WebSocket, set[str]] = {}

    async def connect(self, ws: WebSocket, user_id: str, initial_state: dict) -> None:
        existing = self._connections.get(user_id, [])
        if len(existing) >= _MAX_CONNECTIONS_PER_USER:
            await ws.close(code=4008, reason="Too many connections")
            return

        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)
        self._ws_to_user[ws] = user_id
        self._ws_cameras[ws] = set()
        logger.info("ws_connected", user_id=user_id, total=len(self._ws_to_user))

        try:
            await ws.send_json({"type": "initial_state", **initial_state})
        except Exception:
            pass

    def disconnect(self, ws: WebSocket) -> set[str]:
        """Remove connection, return set of camera_ids this client was viewing."""
        user_id = self._ws_to_user.pop(ws, None)
        cameras = self._ws_cameras.pop(ws, set())
        if user_id and user_id in self._connections:
            try:
                self._connections[user_id].remove(ws)
            except ValueError:
                pass
            if not self._connections[user_id]:
                del self._connections[user_id]
        if user_id:
            logger.info("ws_disconnected", user_id=user_id)
        return cameras

    def track_camera(self, ws: WebSocket, camera_id: str) -> None:
        if ws in self._ws_cameras:
            self._ws_cameras[ws].add(camera_id)

    def untrack_camera(self, ws: WebSocket, camera_id: str) -> None:
        if ws in self._ws_cameras:
            self._ws_cameras[ws].discard(camera_id)

    def camera_viewer_ids(self, camera_id: str) -> set[str]:
        """Return websocket connection IDs (user_ids) viewing a camera."""
        return {
            uid for ws, uid in self._ws_to_user.items()
            if camera_id in self._ws_cameras.get(ws, set())
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(self._ws_to_user.keys()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(ws)

    async def send_to_permission(self, permission: str, message: dict[str, Any], db: AsyncSession) -> None:
        """Send to all users whose role includes the given permission."""
        from sqlalchemy import select
        from app.models.role import Role
        from app.models.user import User

        payload = json.dumps(message)
        for user_id, sockets in list(self._connections.items()):
            result = await db.execute(
                select(Role)
                .join(User, User.role_id == Role.id)
                .where(User.id == user_id)
            )
            role = result.scalar_one_or_none()
            if role and (permission in role.permissions or "system:admin" in role.permissions):
                for ws in list(sockets):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        self.disconnect(ws)

    def connection_count(self) -> int:
        return len(self._ws_to_user)


# Module-level singleton shared across the process
manager = ConnectionManager()


async def _get_initial_state(db: AsyncSession, user_id: str) -> dict:
    """Fetch camera statuses and unread alert count for new connection."""
    try:
        from sqlalchemy import func, select
        from app.models.alert_event import AlertEvent
        from app.models.camera import Camera

        cameras_result = await db.execute(
            select(Camera.id, Camera.status).where(Camera.is_deleted.is_(False))
        )
        camera_statuses = {str(r.id): r.status.value for r in cameras_result.all()}

        alerts_result = await db.execute(
            select(func.count()).select_from(AlertEvent).where(
                AlertEvent.acknowledged.is_(False)
            )
        )
        unread_alerts = alerts_result.scalar_one()

        return {"camera_statuses": camera_statuses, "unread_alerts": unread_alerts}
    except Exception:
        return {"camera_statuses": {}, "unread_alerts": 0}


@router.websocket("/ws/events")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    payload = decode_access_token(token)
    if not payload:
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.sub

    # Verify user is still active in DB
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        await ws.close(code=4001, reason="User not found or inactive")
        return

    initial_state = await _get_initial_state(db, user_id)
    await manager.connect(ws, user_id, initial_state)

    # Track active WebSocket connections on app state for metrics.
    if hasattr(ws.app.state, "ws_connection_count"):
        ws.app.state.ws_connection_count += 1

    # Start heartbeat
    heartbeat_task = asyncio.create_task(_heartbeat(ws))

    hls_manager = getattr(ws.app.state, "hls_manager", None)

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=_PONG_TIMEOUT * 3)
            except asyncio.TimeoutError:
                break
            except WebSocketDisconnect:
                break

            msg_type = data.get("type")
            if msg_type == "pong":
                pass
            elif msg_type == "subscribe_camera":
                camera_id = data.get("camera_id")
                if camera_id:
                    manager.track_camera(ws, camera_id)
                    if hls_manager:
                        hls_manager.add_viewer(camera_id, user_id)
            elif msg_type == "unsubscribe_camera":
                camera_id = data.get("camera_id")
                if camera_id:
                    manager.untrack_camera(ws, camera_id)
                    if hls_manager:
                        hls_manager.remove_viewer(camera_id, user_id)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_handler_error", user_id=user_id)
    finally:
        heartbeat_task.cancel()
        cameras = manager.disconnect(ws)
        if hasattr(ws.app.state, "ws_connection_count"):
            ws.app.state.ws_connection_count = max(0, ws.app.state.ws_connection_count - 1)
        if hls_manager:
            for camera_id in cameras:
                hls_manager.remove_viewer(camera_id, user_id)
                if hls_manager.viewer_count(camera_id) == 0:
                    asyncio.create_task(hls_manager.stop_stream(camera_id))
                    logger.info("hls_auto_stopped_no_viewers", camera_id=camera_id)


async def _heartbeat(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break


async def redis_to_ws_forwarder(redis_url: str) -> None:
    """
    Background task started on app startup.
    Subscribes to nvr:ws:broadcast and nvr:ws:user:* and forwards to ConnectionManager.
    """
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.psubscribe("nvr:ws:*")
        logger.info("redis_ws_forwarder_started")
        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue
            try:
                channel = message.get("channel", "")
                data = json.loads(message["data"])
                if channel == "nvr:ws:broadcast":
                    await manager.broadcast(data)
                elif channel.startswith("nvr:ws:user:"):
                    user_id = channel[len("nvr:ws:user:"):]
                    await manager.send_to_user(user_id, data)
            except Exception:
                logger.exception("redis_ws_forwarder_error")
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("redis_ws_forwarder_fatal")
