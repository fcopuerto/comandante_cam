import hashlib
from datetime import datetime, timezone

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.database import get_db
from app.models.api_key import APIKey
from app.models.camera_permission import CameraPermission
from app.models.user import User
from app.services.auth_service import decode_access_token

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    api_key: str | None = Depends(_api_key_header),
) -> User:
    if credentials:
        return await _auth_via_jwt(request, db, credentials.credentials)
    if api_key:
        return await _auth_via_api_key(request, db, api_key)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _auth_via_jwt(request: Request, db: AsyncSession, token: str) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    request.state.user = user
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


async def _auth_via_api_key(request: Request, db: AsyncSession, raw_key: str) -> User:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
    if api_key.allowed_ips:
        client_ip = request.client.host if request.client else ""
        if client_ip not in api_key.allowed_ips:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    # Update last used
    api_key.last_used_at = datetime.now(timezone.utc)
    api_key.last_used_ip = request.client.host if request.client else None
    request.state.user = user
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


def require_permission(permission: str):
    """Dependency factory — raises 403 if the authenticated user lacks the permission."""

    async def _check(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.models.role import Role
        result = await db.execute(select(Role).where(Role.id == user.role_id))
        role = result.scalar_one_or_none()
        permissions: list[str] = role.permissions if role else []
        if permission not in permissions and "system:admin" not in permissions:
            logger.warning(
                "permission_denied",
                user_id=user.id,
                required=permission,
                request_id=getattr(request.state, "request_id", None),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return user

    return _check


def require_camera_permission(camera_id_param: str, permission: str):
    """
    Dependency factory that checks per-camera access, falling back to role permission.
    Camera-level deny overrides role-level grant.
    """

    async def _check(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        camera_id = request.path_params.get(camera_id_param)
        result = await db.execute(
            select(CameraPermission).where(
                CameraPermission.user_id == user.id,
                CameraPermission.camera_id == camera_id,
            )
        )
        cam_perm = result.scalar_one_or_none()

        perm_field_map = {
            "view_live": "can_view_live",
            "view_recordings": "can_view_recordings",
            "export_clips": "can_export_clips",
            "configure": "can_configure",
            "ptz": "can_ptz",
        }
        action = permission.split(":")[-1]
        field = perm_field_map.get(action)

        if cam_perm and field:
            if not getattr(cam_perm, field, False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Camera permission denied: cameras:{action}",
                )
            return user

        # Fall back to role-level check
        from app.models.role import Role
        role_result = await db.execute(select(Role).where(Role.id == user.role_id))
        role = role_result.scalar_one_or_none()
        role_permissions: list[str] = role.permissions if role else []
        if permission not in role_permissions and "system:admin" not in role_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return user

    return _check
