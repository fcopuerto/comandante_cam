from math import ceil

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit_service as audit_svc
import app.services.user_service as user_svc
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.models.session import UserSession
from app.models.user import User
from app.schemas.camera import CameraPermissionSet, Page
from app.schemas.user import UserCreate, UserInvite, UserResponse, UserSessionResponse, UserUpdate

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_id=user.role_id,
        is_active=user.is_active,
        is_mfa_enabled=user.is_mfa_enabled,
        must_change_password=user.must_change_password,
        failed_login_count=user.failed_login_count,
        last_login=user.last_login,
        last_login_ip=user.last_login_ip,
        preferred_language=user.preferred_language,
        preferred_timezone=user.preferred_timezone,
        created_at=user.created_at,
        updated_at=user.updated_at,
        created_by=user.created_by,
        anonymised_at=user.anonymised_at,
    )


# ── List / Create ─────────────────────────────────────────────────────────────

@router.get("", response_model=Page[UserResponse])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> Page[UserResponse]:
    from sqlalchemy import func, or_
    stmt = select(User)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(stmt.order_by(User.created_at.desc()).offset(offset).limit(page_size))
    users = list(result.scalars().all())
    return Page(
        items=[_user_response(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request=Depends(lambda: None),
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> UserResponse:
    from fastapi import Request as FastAPIRequest
    try:
        user = await user_svc.create_user(db, body, acting_user)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ValidationError, NotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit_svc.log(db, "user_created", acting_user, "user", user.id)
    return _user_response(user)


# ── Invite ────────────────────────────────────────────────────────────────────

@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserInvite,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> UserResponse:
    import secrets
    from sqlalchemy import select as sa_select
    from app.models.role import Role

    result = await db.execute(sa_select(Role).where(Role.name == body.role))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown role: {body.role}")

    temp_password = secrets.token_urlsafe(12) + "!A1"  # satisfies length, upper, digit, special
    create_data = UserCreate(
        email=body.email,
        full_name=body.full_name,
        password=temp_password,
        role_id=str(role.id),
    )
    try:
        user = await user_svc.create_user(db, create_data, acting_user)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ValidationError, NotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    audit_svc.log(db, "user_invited", acting_user, "user", user.id)

    import asyncio
    from app.services.notification_service import send_invite_email
    try:
        await asyncio.to_thread(send_invite_email, body.email, body.full_name, temp_password)
    except Exception:
        logger.warning("invite_email_failed", email=body.email)

    return _user_response(user)


# ── Get / Update / Delete ─────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> UserResponse:
    try:
        user = await user_svc._load_user(db, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _user_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> UserResponse:
    try:
        user = await user_svc.update_user(db, user_id, body, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValidationError, NotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit_svc.log(db, "user_updated", acting_user, "user", user_id)
    return _user_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    """GDPR soft-delete via anonymisation — no hard delete."""
    try:
        await user_svc.anonymise_user(db, user_id, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_svc.log(db, "user_anonymised", acting_user, "user", user_id, severity="security")


# ── State management ──────────────────────────────────────────────────────────

@router.post("/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    try:
        await user_svc.deactivate_user(db, user_id, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_svc.log(db, "user_deactivated", acting_user, "user", user_id, severity="security")


@router.post("/{user_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    try:
        await user_svc.activate_user(db, user_id, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_svc.log(db, "user_activated", acting_user, "user", user_id)


@router.post("/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    try:
        await user_svc.unlock_user(db, user_id, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_svc.log(db, "user_unlocked", acting_user, "user", user_id)


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/{user_id}/sessions", response_model=list[UserSessionResponse])
async def list_user_sessions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> list[UserSessionResponse]:
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        UserSessionResponse(
            id=s.id,
            device_name=s.device_name,
            ip_address=s.ip_address,
            last_used_at=s.last_used_at,
            created_at=s.created_at,
            expires_at=s.expires_at,
            is_revoked=s.is_revoked,
        )
        for s in sessions
    ]


@router.delete("/{user_id}/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_user_sessions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    from datetime import datetime, timezone
    from sqlalchemy import update
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_revoked.is_(False))
        .values(
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
            revoked_reason="admin_revoke",
        )
    )
    audit_svc.log(db, "sessions_revoked", acting_user, "user", user_id, severity="security")


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/{user_id}/audit-log", response_model=Page)
async def get_user_audit_log(
    user_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> Page:
    from sqlalchemy import func
    from app.models.audit_log import AuditLog
    from app.schemas.user import AuditLogResponse
    stmt = select(AuditLog).where(AuditLog.user_id == user_id)
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    entries = result.scalars().all()
    items = [
        AuditLogResponse(
            id=e.id, user_id=e.user_id, user_email=e.user_email,
            action=e.action, resource_type=e.resource_type, resource_id=e.resource_id,
            detail=e.detail, ip_address=e.ip_address, request_id=e.request_id,
            severity=e.severity, created_at=e.created_at,
        )
        for e in entries
    ]
    return Page(items=items, total=total, page=page, page_size=page_size,
                pages=ceil(total / page_size) if total else 0)


# ── Camera permissions ────────────────────────────────────────────────────────

@router.patch("/{user_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_camera_permissions(
    user_id: str,
    body: list[CameraPermissionSet],
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("users:manage")),
) -> None:
    try:
        await user_svc.set_camera_permissions(db, user_id, body, acting_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_svc.log(db, "permission_updated", acting_user, "user", user_id)
