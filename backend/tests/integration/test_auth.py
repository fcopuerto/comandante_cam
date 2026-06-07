"""
Integration tests for the authentication system.
Requires: PostgreSQL test DB, fakeredis for Redis isolation.

Run with: docker compose exec backend pytest tests/integration/test_auth.py -v
"""
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport
from freezegun import freeze_time

import app.services.auth_service as auth_svc
from app.main import create_app
from app.database import get_db
from app.redis_client import get_redis
from app.models.role import Role
from app.models.user import User
from app.models.session import UserSession


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def auth_client(db_session, fake_redis):
    app = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def viewer_role(db_session) -> Role:
    role = Role(name="viewer", permissions=["cameras:view_live"], is_system_role=True)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def test_user(db_session, viewer_role) -> User:
    user = User(
        email="test@example.com",
        full_name="Test User",
        hashed_password=auth_svc.hash_password("Correct!Password1"),
        role_id=viewer_role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, email="test@example.com", password="Correct!Password1", mfa_code=None):
    body = {"email": email, "password": password}
    if mfa_code:
        body["mfa_code"] = mfa_code
    return await client.post("/api/v1/auth/login", json=body)


# ── login tests ───────────────────────────────────────────────────────────────

async def test_login_success(auth_client, test_user):
    resp = await _login(auth_client)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "nvr_refresh" in resp.cookies


async def test_login_wrong_password_returns_401(auth_client, test_user):
    resp = await _login(auth_client, password="WrongPassword1!")
    assert resp.status_code == 401
    # Must never say which credential was wrong
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_wrong_password_increments_fail_count(auth_client, test_user, db_session):
    await _login(auth_client, password="WrongPassword1!")
    await db_session.refresh(test_user)
    assert test_user.failed_login_count == 1


async def test_five_failures_cause_lockout(auth_client, test_user):
    for _ in range(5):
        await _login(auth_client, password="WrongPassword1!")
    # 6th attempt — should be locked
    resp = await _login(auth_client, password="Correct!Password1")
    assert resp.status_code == 401
    assert "locked" in resp.json()["detail"].lower()


async def test_correct_login_resets_fail_count(auth_client, test_user, db_session):
    await _login(auth_client, password="WrongPassword1!")
    await _login(auth_client)  # success
    await db_session.refresh(test_user)
    assert test_user.failed_login_count == 0


async def test_inactive_user_cannot_login(auth_client, db_session, viewer_role):
    inactive = User(
        email="inactive@example.com",
        full_name="Inactive",
        hashed_password=auth_svc.hash_password("Correct!Password1"),
        role_id=viewer_role.id,
        is_active=False,
    )
    db_session.add(inactive)
    await db_session.flush()
    resp = await _login(auth_client, email="inactive@example.com")
    assert resp.status_code == 401


# ── JWT validation ────────────────────────────────────────────────────────────

async def test_valid_jwt_authenticates(auth_client, test_user, viewer_role):
    login_resp = await _login(auth_client)
    token = login_resp.json()["access_token"]
    resp = await auth_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user.email


async def test_expired_jwt_returns_401(auth_client, test_user):
    with freeze_time("2020-01-01"):
        login_resp = await _login(auth_client)
        token = login_resp.json()["access_token"]
    # Token is now expired (created in 2020, we're past exp)
    resp = await auth_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_invalid_jwt_returns_401(auth_client, test_user):
    resp = await auth_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert resp.status_code == 401


# ── refresh token rotation ────────────────────────────────────────────────────

async def test_refresh_issues_new_token(auth_client, test_user):
    await _login(auth_client)
    resp = await auth_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert "nvr_refresh" in resp.cookies


async def test_old_refresh_token_invalid_after_rotation(auth_client, test_user, db_session):
    login_resp = await _login(auth_client)
    old_token = login_resp.cookies.get("nvr_refresh")

    # Rotate
    await auth_client.post("/api/v1/auth/refresh")

    # Try to use old token manually
    auth_client.cookies.set("nvr_refresh", old_token)
    resp = await auth_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


async def test_refresh_token_reuse_revokes_all_sessions(auth_client, test_user, db_session):
    """Double-spend: using a revoked refresh token must revoke ALL sessions."""
    login_resp = await _login(auth_client)
    old_token = login_resp.cookies.get("nvr_refresh")

    # Normal rotation
    await auth_client.post("/api/v1/auth/refresh")

    # Reuse the old (now revoked) token — should trigger reuse detection
    auth_client.cookies.set("nvr_refresh", old_token)
    resp = await auth_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401

    # All sessions for the user must be revoked
    from sqlalchemy import select
    result = await db_session.execute(
        select(UserSession).where(UserSession.user_id == test_user.id)
    )
    sessions = result.scalars().all()
    assert all(s.is_revoked for s in sessions)


# ── MFA ───────────────────────────────────────────────────────────────────────

async def test_login_without_mfa_code_when_mfa_enabled(auth_client, db_session, test_user):
    import pyotp
    from app.utils.encryption import get_encryption
    secret = pyotp.random_base32()
    test_user.mfa_secret = get_encryption().encrypt(secret)
    test_user.is_mfa_enabled = True
    await db_session.flush()

    resp = await _login(auth_client)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_with_correct_totp(auth_client, db_session, test_user):
    import pyotp
    from app.utils.encryption import get_encryption
    secret = pyotp.random_base32()
    test_user.mfa_secret = get_encryption().encrypt(secret)
    test_user.is_mfa_enabled = True
    await db_session.flush()

    code = pyotp.TOTP(secret).now()
    resp = await _login(auth_client, mfa_code=code)
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_with_wrong_totp_returns_401(auth_client, db_session, test_user):
    import pyotp
    from app.utils.encryption import get_encryption
    secret = pyotp.random_base32()
    test_user.mfa_secret = get_encryption().encrypt(secret)
    test_user.is_mfa_enabled = True
    await db_session.flush()

    resp = await _login(auth_client, mfa_code="000000")
    assert resp.status_code == 401


# ── rate limit ────────────────────────────────────────────────────────────────

async def test_rate_limit_on_login(auth_client, test_user):
    """11 login requests in 10 min from same IP → 429."""
    for i in range(10):
        await auth_client.post(
            "/api/v1/auth/login",
            json={"email": f"nope{i}@x.com", "password": "Whatever1!"},
        )
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "last@x.com", "password": "Whatever1!"},
    )
    assert resp.status_code == 429


# ── security: no secrets in logs ─────────────────────────────────────────────

async def test_no_password_in_login_error_response(auth_client, test_user):
    resp = await _login(auth_client, password="MySecretPass1!")
    assert resp.status_code == 401
    body = resp.text
    assert "MySecretPass1!" not in body
    assert "password" not in body.lower() or "Invalid credentials" in body


async def test_no_token_in_error_response(auth_client, test_user):
    resp = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer fake.token.here"},
    )
    assert resp.status_code == 401
    assert "fake.token.here" not in resp.text
