import hashlib
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.camera_permission import CameraPermission
from app.models.role import Role
from app.models.session import UserSession
from app.models.user import User
from app.schemas.camera import CameraPermissionSet
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import hash_password, validate_password_strength

logger = structlog.get_logger(__name__)


async def _load_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", user_id)
    return user


async def create_user(
    db: AsyncSession,
    data: UserCreate,
    created_by: User,
) -> User:
    # Password strength
    failures = validate_password_strength(data.password)
    if failures:
        raise ValidationError("password", "; ".join(failures))

    # Duplicate email check
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Email {data.email} is already registered")

    # Role validation
    if data.role_id:
        role_result = await db.execute(select(Role).where(Role.id == data.role_id))
        role = role_result.scalar_one_or_none()
        if not role:
            raise NotFoundError("Role", data.role_id)
        # Only system:admin users can assign superadmin role
        acting_role_result = await db.execute(select(Role).where(Role.id == created_by.role_id))
        acting_role = acting_role_result.scalar_one_or_none()
        acting_perms = acting_role.permissions if acting_role else []
        if role.name == "superadmin" and "system:admin" not in acting_perms:
            raise ValidationError("role_id", "Only superadmin users can assign the superadmin role")

    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role_id=data.role_id,
        must_change_password=True,
        preferred_language=data.preferred_language,
        preferred_timezone=data.preferred_timezone,
        created_by=created_by.id,
    )
    db.add(user)
    await db.flush()
    logger.info("user_created", user_id=user.id, created_by=created_by.id)
    return user


async def update_user(
    db: AsyncSession,
    user_id: str,
    data: UserUpdate,
    acting_user: User,
) -> User:
    user = await _load_user(db, user_id)

    if data.role_id is not None and data.role_id != user.role_id:
        # Check acting user has permission to assign this role
        role_result = await db.execute(select(Role).where(Role.id == data.role_id))
        role = role_result.scalar_one_or_none()
        if not role:
            raise NotFoundError("Role", data.role_id)
        acting_role_result = await db.execute(select(Role).where(Role.id == acting_user.role_id))
        acting_role = acting_role_result.scalar_one_or_none()
        acting_perms = acting_role.permissions if acting_role else []
        if role.name == "superadmin" and "system:admin" not in acting_perms:
            raise ValidationError("role_id", "Only superadmin users can assign the superadmin role")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    logger.info("user_updated", user_id=user_id, acting_user=acting_user.id)
    return user


async def deactivate_user(
    db: AsyncSession,
    user_id: str,
    acting_user: User,
) -> None:
    user = await _load_user(db, user_id)
    user.is_active = False
    # Revoke all active sessions
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_revoked.is_(False))
        .values(
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
            revoked_reason="admin_deactivated",
        )
    )
    logger.info("user_deactivated", user_id=user_id, acting_user=acting_user.id)


async def activate_user(
    db: AsyncSession,
    user_id: str,
    acting_user: User,
) -> None:
    user = await _load_user(db, user_id)
    user.is_active = True
    logger.info("user_activated", user_id=user_id, acting_user=acting_user.id)


async def anonymise_user(
    db: AsyncSession,
    user_id: str,
    acting_user: User,
) -> None:
    """GDPR right to erasure — replaces PII while preserving referential integrity."""
    user = await _load_user(db, user_id)

    email_hash = hashlib.sha256(user.email.encode()).hexdigest()[:16]
    user.email = f"{email_hash}@deleted.local"
    user.full_name = "Deleted User"
    # Set to an invalid hash so the account can never be used
    user.hashed_password = "!ANONYMISED!"
    user.mfa_secret = None
    user.mfa_backup_codes = None
    user.last_login_ip = None
    user.is_active = False
    user.anonymised_at = datetime.now(timezone.utc)

    # Revoke all sessions
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_revoked.is_(False))
        .values(
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
            revoked_reason="gdpr_erasure",
        )
    )
    logger.info("user_anonymised", user_id=user_id, acting_user=acting_user.id)


async def unlock_user(
    db: AsyncSession,
    user_id: str,
    acting_user: User,
) -> None:
    user = await _load_user(db, user_id)
    user.failed_login_count = 0
    user.locked_until = None
    logger.info("user_unlocked", user_id=user_id, acting_user=acting_user.id)


async def set_camera_permissions(
    db: AsyncSession,
    user_id: str,
    permissions: list[CameraPermissionSet],
    acting_user: User,
) -> None:
    await _load_user(db, user_id)  # verify user exists
    for perm_set in permissions:
        existing = await db.execute(
            select(CameraPermission).where(
                CameraPermission.user_id == user_id,
                CameraPermission.camera_id == perm_set.camera_id,
            )
        )
        perm = existing.scalar_one_or_none()
        if perm is None:
            perm = CameraPermission(
                user_id=user_id,
                camera_id=perm_set.camera_id,
                granted_by=acting_user.id,
            )
            db.add(perm)
        perm.can_view_live = perm_set.can_view_live
        perm.can_view_recordings = perm_set.can_view_recordings
        perm.can_export_clips = perm_set.can_export_clips
        perm.can_configure = perm_set.can_configure
        perm.can_ptz = perm_set.can_ptz
    await db.flush()
