import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AccountLockedError, AuthenticationError
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.utils.encryption import get_encryption

logger = structlog.get_logger(__name__)

ALGORITHM = "RS256"
LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes


_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=1)


# ── RSA key helpers ───────────────────────────────────────────────────────────

def _read_private_key() -> str:
    return get_settings().RSA_PRIVATE_KEY_PATH.read_text()


def _read_public_key() -> str:
    return get_settings().RSA_PUBLIC_KEY_PATH.read_text()


def load_rsa_keys() -> tuple[str, str]:
    """Load and validate RSA key pair. Raises on missing or invalid keys."""
    private_pem = _read_private_key()
    public_pem = _read_public_key()
    # Validate by round-tripping a test token
    test = jwt.encode({"sub": "test"}, private_pem, algorithm=ALGORITHM)
    jwt.decode(test, public_pem, algorithms=[ALGORITHM])
    return private_pem, public_pem


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_password_strength(password: str) -> list[str]:
    """Returns a list of failure reasons; empty list means the password is acceptable."""
    failures: list[str] = []
    if len(password) < 12:
        failures.append("Must be at least 12 characters")
    if not any(c.isupper() for c in password):
        failures.append("Must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        failures.append("Must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        failures.append("Must contain at least one digit")
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        failures.append("Must contain at least one special character")
    return failures


async def check_hibp(password: str) -> bool:
    """Return True if the password appears in the HaveIBeenPwned database (k-anonymity lookup)."""
    import httpx

    sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    settings = get_settings()
    headers = {}
    if settings.HIBP_API_KEY:
        headers["hibp-api-key"] = settings.HIBP_API_KEY
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers=headers,
            )
        for line in resp.text.splitlines():
            hash_suffix, _ = line.split(":")
            if hash_suffix == suffix:
                return True
    except Exception:
        # Fail open — don't block login if HIBP is unreachable
        logger.warning("hibp_check_failed")
    return False


# ── Tokens ────────────────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    role_name: str,
    permissions: list[str],
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role_name,
        "permissions": permissions,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _read_private_key(), algorithm=ALGORITHM)


def create_refresh_token() -> str:
    return str(uuid.uuid4())


def decode_access_token(token: str) -> TokenPayload | None:
    try:
        payload = jwt.decode(token, _read_public_key(), algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except (JWTError, Exception):
        return None


# ── Sessions ──────────────────────────────────────────────────────────────────

def _parse_device_name(user_agent: str) -> str:
    ua = user_agent.lower()
    if "chrome" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Unknown browser"
    if "windows" in ua:
        os_ = "Windows"
    elif "mac" in ua:
        os_ = "macOS"
    elif "linux" in ua:
        os_ = "Linux"
    elif "android" in ua:
        os_ = "Android"
    elif "iphone" in ua or "ipad" in ua:
        os_ = "iOS"
    else:
        os_ = "Unknown OS"
    return f"{browser} on {os_}"


async def create_session(
    db: AsyncSession,
    user_id: str,
    refresh_token: str,
    ip_address: str | None,
    user_agent: str,
) -> UserSession:
    settings = get_settings()
    device_fp = hashlib.sha256(user_agent.encode()).hexdigest()
    session = UserSession(
        id=refresh_token,
        user_id=user_id,
        device_name=_parse_device_name(user_agent),
        device_fingerprint=device_fp,
        ip_address=ip_address,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    return session


async def validate_refresh_token(db: AsyncSession, token: str) -> UserSession | None:
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == token,
            UserSession.is_revoked.is_(False),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.last_used_at = datetime.now(timezone.utc)
    return session


async def rotate_refresh_token(db: AsyncSession, session: UserSession) -> str:
    session.is_revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = "rotated"

    new_token = create_refresh_token()
    settings = get_settings()
    new_session = UserSession(
        id=new_token,
        user_id=session.user_id,
        device_name=session.device_name,
        device_fingerprint=session.device_fingerprint,
        ip_address=session.ip_address,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_session)
    return new_token


async def detect_refresh_token_reuse(db: AsyncSession, token: str) -> bool:
    """
    If a revoked token is presented again, it means double-spend — revoke ALL sessions
    for that user to contain the potential breach.
    """
    result = await db.execute(select(UserSession).where(UserSession.id == token))
    session = result.scalar_one_or_none()
    if session and session.is_revoked:
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == session.user_id, UserSession.is_revoked.is_(False))
            .values(
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
                revoked_reason="reuse_detected",
            )
        )
        logger.warning(
            "refresh_token_reuse_detected",
            user_id=session.user_id,
        )
        return True
    return False


# ── Login lockout (Redis) ─────────────────────────────────────────────────────

@dataclass
class LockoutState:
    is_locked: bool
    attempts: int
    ttl_seconds: int | None


async def check_lockout(redis, identifier: str) -> LockoutState:
    key = f"lockout:{identifier}"
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    count_raw, ttl = await pipe.execute()
    attempts = int(count_raw) if count_raw else 0
    return LockoutState(
        is_locked=attempts >= LOCKOUT_MAX_ATTEMPTS,
        attempts=attempts,
        ttl_seconds=ttl if ttl > 0 else None,
    )


async def record_failed_attempt(redis, identifier: str) -> None:
    key = f"lockout:{identifier}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCKOUT_DURATION_SECONDS)
    await pipe.execute()


async def clear_lockout(redis, identifier: str) -> None:
    await redis.delete(f"lockout:{identifier}")


# ── Authenticate ──────────────────────────────────────────────────────────────

async def authenticate(
    db: AsyncSession,
    redis,
    email: str,
    password: str,
    mfa_code: str | None,
    ip: str,
) -> User:
    """
    Validates credentials and returns the authenticated User.
    Raises AuthenticationError with a safe generic message on any failure —
    never distinguish between wrong email and wrong password.
    """
    ip_state = await check_lockout(redis, f"ip:{ip}")
    email_state = await check_lockout(redis, f"email:{email}")
    if ip_state.is_locked or email_state.is_locked:
        raise AccountLockedError("Account temporarily locked due to too many failed attempts")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await record_failed_attempt(redis, f"ip:{ip}")
        await record_failed_attempt(redis, f"email:{email}")
        raise AuthenticationError("Invalid credentials")

    if not verify_password(password, user.hashed_password):
        await record_failed_attempt(redis, f"ip:{ip}")
        await record_failed_attempt(redis, f"email:{email}")
        user.failed_login_count = (user.failed_login_count or 0) + 1
        await db.flush()
        raise AuthenticationError("Invalid credentials")

    if user.is_mfa_enabled:
        if not mfa_code:
            raise AuthenticationError("MFA code required")
        if not _verify_mfa(user, mfa_code):
            await record_failed_attempt(redis, f"ip:{ip}")
            await record_failed_attempt(redis, f"email:{email}")
            raise AuthenticationError("Invalid MFA code")

    # Success — reset failure counters
    user.failed_login_count = 0
    user.last_login = datetime.now(timezone.utc)
    user.last_login_ip = ip
    await db.flush()
    await clear_lockout(redis, f"ip:{ip}")
    await clear_lockout(redis, f"email:{email}")
    return user


def _verify_mfa(user: User, code: str) -> bool:
    if not user.mfa_secret:
        return False
    secret = get_encryption().decrypt(user.mfa_secret)
    totp = pyotp.TOTP(secret)
    if totp.verify(code, valid_window=1):
        return True
    return _check_and_consume_backup_code(user, code)


def _check_and_consume_backup_code(user: User, code: str) -> bool:
    codes: list[dict] = user.mfa_backup_codes or []
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    for entry in codes:
        if entry.get("code_hash") == code_hash and not entry.get("used"):
            entry["used"] = True
            user.mfa_backup_codes = codes
            return True
    return False


# ── MFA setup ─────────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="NVR Pro")


def generate_backup_codes() -> tuple[list[str], list[dict]]:
    """Returns (plaintext_codes, hashed_entries) — store only the hashed entries."""
    codes = [secrets.token_hex(5).upper() for _ in range(10)]
    entries = [{"code_hash": hashlib.sha256(c.encode()).hexdigest(), "used": False} for c in codes]
    return codes, entries
