import base64
import io
from datetime import datetime, timezone

import pyotp
import qrcode
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.auth_service as auth_svc
from app.config import get_settings
from app.core.exceptions import AccountLockedError, AuthenticationError, ValidationError
from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.role import Role
from app.models.session import UserSession
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.auth import (
    BackupCodesResponse,
    ChangePasswordRequest,
    CheckPasswordRequest,
    CheckPasswordResponse,
    LoginRequest,
    MFADisableRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    SessionResponse,
    TokenResponse,
    UserMeResponse,
)
from app.utils.encryption import get_encryption

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "nvr_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        domain=settings.COOKIE_DOMAIN or None,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


async def _build_token_response(user: User, db: AsyncSession) -> dict:
    from app.schemas.user import UserResponse
    await db.refresh(user)
    result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = result.scalar_one_or_none()
    role_name = role.name if role else ""
    permissions = role.permissions if role else []
    access_token = auth_svc.create_access_token(
        user_id=user.id,
        email=user.email,
        role_name=role_name,
        permissions=permissions,
    )
    settings = get_settings()
    user_data = UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role_id=str(user.role_id) if user.role_id else None,
        role=role_name or None,
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
        created_by=str(user.created_by) if user.created_by else None,
        anonymised_at=user.anonymised_at,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_data.model_dump(mode="json"),
    }


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/10minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    try:
        user = await auth_svc.authenticate(
            db=db,
            redis=redis,
            email=body.email,
            password=body.password,
            mfa_code=body.mfa_code,
            ip=ip,
        )
    except AccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account temporarily locked due to too many failed attempts",
        ) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc

    refresh_token = auth_svc.create_refresh_token()
    await auth_svc.create_session(
        db=db,
        user_id=user.id,
        refresh_token=refresh_token,
        ip_address=ip,
        user_agent=request.headers.get("user-agent", ""),
    )
    _set_refresh_cookie(response, refresh_token)
    token_data = await _build_token_response(user, db)
    logger.info("user_login", user_id=user.id)
    return TokenResponse(**token_data)


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("60/hour")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    # Check for reuse of a revoked token — double-spend detection
    if await auth_svc.detect_refresh_token_reuse(db, token):
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated — please log in again",
        )

    session = await auth_svc.validate_refresh_token(db, token)
    if not session:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    new_token = await auth_svc.rotate_refresh_token(db, session)
    _set_refresh_cookie(response, new_token)
    token_data = await _build_token_response(user, db)
    return TokenResponse(**token_data)


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        result = await db.execute(
            select(UserSession).where(UserSession.id == token, UserSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.is_revoked = True
            session.revoked_at = datetime.now(timezone.utc)
            session.revoked_reason = "logout"
    _clear_refresh_cookie(response)
    logger.info("user_logout", user_id=user.id)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    from sqlalchemy import update
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.is_revoked.is_(False))
        .values(
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
            revoked_reason="logout_all",
        )
    )
    _clear_refresh_cookie(response)
    logger.info("user_logout_all", user_id=user.id)


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserMeResponse:
    result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = result.scalar_one_or_none()
    return UserMeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=role.name if role else None,
        permissions=role.permissions if role else [],
        is_mfa_enabled=user.is_mfa_enabled,
        must_change_password=user.must_change_password,
        preferred_timezone=user.preferred_timezone,
        preferred_language=user.preferred_language,
        created_at=user.created_at,
    )


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    current_token = request.cookies.get(REFRESH_COOKIE)
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.is_revoked.is_(False),
        )
    )
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            device_name=s.device_name,
            ip_address=s.ip_address,
            last_used_at=s.last_used_at,
            created_at=s.created_at,
            expires_at=s.expires_at,
            is_current=(s.id == current_token),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id, UserSession.user_id == user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.is_revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = "revoked_by_user"


# ── MFA ───────────────────────────────────────────────────────────────────────

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    if user.is_mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA already enabled")
    secret = auth_svc.generate_totp_secret()
    uri = auth_svc.get_totp_provisioning_uri(secret, user.email)
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    # Persist encrypted secret (not yet activated — activated on /mfa/verify)
    user.mfa_secret = get_encryption().encrypt(secret)
    return MFASetupResponse(secret=secret, otpauth_uri=uri, qr_data_url=qr_data_url)


@router.post("/mfa/verify", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_verify(
    body: MFAVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run /mfa/setup first")
    secret = get_encryption().decrypt(user.mfa_secret)
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    user.is_mfa_enabled = True
    _, entries = auth_svc.generate_backup_codes()
    user.mfa_backup_codes = entries
    logger.info("mfa_enabled", user_id=user.id)


@router.delete("/mfa", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(
    body: MFADisableRequest,
    user: User = Depends(get_current_user),
) -> None:
    if not user.is_mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not enabled")
    if not auth_svc._verify_mfa(user, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    user.is_mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    logger.info("mfa_disabled", user_id=user.id)


@router.get("/mfa/backup-codes", response_model=BackupCodesResponse)
async def get_backup_codes(
    user: User = Depends(get_current_user),
) -> BackupCodesResponse:
    if not user.is_mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not enabled")
    # Return only whether codes are used — never the plaintext codes again
    codes = user.mfa_backup_codes or []
    remaining = [f"****{i+1:02d}" for i, c in enumerate(codes) if not c.get("used")]
    return BackupCodesResponse(codes=remaining)


@router.post("/mfa/backup-codes/regenerate", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    body: MFAVerifyRequest,
    user: User = Depends(get_current_user),
) -> BackupCodesResponse:
    if not user.is_mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not enabled")
    if not auth_svc._verify_mfa(user, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    plaintext_codes, entries = auth_svc.generate_backup_codes()
    user.mfa_backup_codes = entries
    return BackupCodesResponse(codes=plaintext_codes)


# ── Password ──────────────────────────────────────────────────────────────────

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not auth_svc.verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wrong current password")
    failures = auth_svc.validate_password_strength(body.new_password)
    if failures:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "weak_password", "reasons": failures},
        )
    user.hashed_password = auth_svc.hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.must_change_password = False
    logger.info("password_changed", user_id=user.id)


@router.post("/check-password", response_model=CheckPasswordResponse)
async def check_password(body: CheckPasswordRequest) -> CheckPasswordResponse:
    pwned = await auth_svc.check_hibp(body.password)
    return CheckPasswordResponse(
        pwned=pwned,
        message="This password has appeared in a data breach." if pwned else "Password not found in known breaches.",
    )
