"""
WebSocket SSH terminal proxy.
Auth via ?token=<access_token> query param (same pattern as ws.py).
"""
import asyncio

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionFactory
from app.models.equipment import Equipment
from app.services.auth_service import decode_access_token
from app.utils.encryption import get_encryption

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["terminal"])


@router.websocket("/ws/terminal/{equipment_id}")
async def terminal_ws(
    websocket: WebSocket,
    equipment_id: str,
    token: str = Query(...),
) -> None:
    try:
        import asyncssh
    except ImportError:
        await websocket.accept()
        await websocket.send_text("\r\nasyncssh is not installed on the server.\r\n")
        await websocket.close()
        return

    # --- Auth ---
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    # --- Load equipment ---
    async with AsyncSessionFactory() as db:
        eq = await db.get(Equipment, equipment_id)
        if not eq or not eq.is_active:
            await websocket.send_text("\r\nDevice not found or inactive.\r\n")
            await websocket.close(code=4004, reason="Not found")
            return
        enc = get_encryption()
        ssh_password = enc.decrypt(eq.ssh_password_enc) if eq.ssh_password_enc else None
        ssh_host = eq.ip_address
        ssh_port = eq.ssh_port
        ssh_user = eq.ssh_user
        ssh_key = eq.ssh_key_path

    logger.info("terminal_connecting", equipment_id=equipment_id, host=ssh_host, user=payload.sub)

    connect_kwargs: dict = {
        "host": ssh_host,
        "port": ssh_port,
        "username": ssh_user,
        "known_hosts": None,
    }
    if ssh_password:
        connect_kwargs["password"] = ssh_password
    elif ssh_key:
        connect_kwargs["client_keys"] = [ssh_key]

    try:
        async with asyncssh.connect(**connect_kwargs) as conn:
            async with conn.create_process(
                term_type="xterm-256color", request_pty=True
            ) as proc:
                logger.info("terminal_connected", equipment_id=equipment_id, user=payload.sub)

                async def _ws_to_ssh() -> None:
                    try:
                        while True:
                            data = await websocket.receive_text()
                            proc.stdin.write(data)
                    except (WebSocketDisconnect, Exception):
                        proc.stdin.write_eof()

                async def _ssh_to_ws() -> None:
                    try:
                        async for chunk in proc.stdout:
                            await websocket.send_text(chunk)
                    except Exception:
                        pass

                await asyncio.gather(_ws_to_ssh(), _ssh_to_ws(), return_exceptions=True)

    except asyncssh.DisconnectError as exc:
        logger.info("terminal_disconnected", equipment_id=equipment_id, reason=str(exc))
    except asyncssh.Error as exc:
        logger.warning("terminal_ssh_error", equipment_id=equipment_id, error=str(exc))
        try:
            await websocket.send_text(f"\r\n\x1b[31mSSH error: {exc}\x1b[0m\r\n")
            await websocket.close()
        except Exception:
            pass
    except Exception:
        logger.exception("terminal_unexpected_error", equipment_id=equipment_id)
        try:
            await websocket.close()
        except Exception:
            pass
