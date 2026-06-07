"""
Append-only audit log service.
All writes are fire-and-forget via asyncio.create_task so they never delay responses.
"""
import asyncio
from typing import Any

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

logger = structlog.get_logger(__name__)

# Keys containing these substrings are removed from detail before logging
_SENSITIVE_SUBSTRINGS = frozenset({
    "password", "token", "secret", "key", "credential",
    "hash", "fernet", "encrypt", "private",
})


def _sanitise_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively strip keys whose names contain sensitive substrings."""
    if detail is None:
        return None
    result: dict[str, Any] = {}
    for k, v in detail.items():
        k_lower = k.lower()
        if any(s in k_lower for s in _SENSITIVE_SUBSTRINGS):
            continue
        if isinstance(v, dict):
            result[k] = _sanitise_detail(v)
        elif isinstance(v, list):
            result[k] = [
                _sanitise_detail(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


async def _write_log(
    db: AsyncSession,
    action: str,
    user: User | None,
    resource_type: str | None,
    resource_id: str | None,
    detail: dict | None,
    request: Request | None,
    severity: str,
) -> None:
    try:
        entry = AuditLog(
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            detail=_sanitise_detail(detail),
            ip_address=(
                request.client.host if request and request.client else None
            ),
            user_agent=(
                request.headers.get("user-agent") if request else None
            ),
            request_id=(
                getattr(request.state, "request_id", None) if request else None
            ),
            severity=severity,
        )
        db.add(entry)
        await db.flush()
    except Exception:
        logger.exception("audit_log_write_failed", action=action)


def log(
    db: AsyncSession,
    action: str,
    user: User | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    detail: dict | None = None,
    request: Request | None = None,
    severity: str = "info",
) -> None:
    """Fire-and-forget audit log write. Never blocks the caller."""
    try:
        asyncio.get_running_loop().create_task(
            _write_log(db, action, user, resource_type, resource_id, detail, request, severity)
        )
    except RuntimeError:
        # No running loop (e.g. in tests calling synchronously) — skip
        pass
