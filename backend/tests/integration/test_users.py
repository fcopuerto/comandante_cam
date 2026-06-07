"""
Integration tests for Session 6: user management, roles, audit log, GDPR.

Run with: docker compose exec backend pytest tests/integration/test_users.py -v
"""
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport

import app.services.auth_service as auth_svc
from app.database import get_db
from app.main import create_app
from app.models.role import Role
from app.models.user import User
from app.redis_client import get_redis


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def app_client(db_session, fake_redis):
    application = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_redis] = override_redis

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def admin_role(db_session) -> Role:
    role = Role(
        name="admin",
        display_name="Administrator",
        permissions=["users:manage", "roles:manage", "system:audit", "system:admin", "cameras:manage"],
        is_system_role=True,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def viewer_role(db_session) -> Role:
    role = Role(
        name="viewer",
        display_name="Viewer",
        permissions=["cameras:view"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def manager_role(db_session) -> Role:
    role = Role(
        name="manager",
        display_name="Manager",
        permissions=["users:manage", "roles:manage", "cameras:manage", "cameras:configure"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def superadmin_role(db_session) -> Role:
    role = Role(
        name="superadmin",
        display_name="Super Admin",
        permissions=["system:admin"],
        is_system_role=True,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def admin_user(db_session, admin_role) -> User:
    user = User(
        email="admin@example.com",
        full_name="Admin User",
        hashed_password=auth_svc.hash_password("Admin!Pass1"),
        role_id=admin_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session, viewer_role) -> User:
    user = User(
        email="viewer@example.com",
        full_name="Viewer User",
        hashed_password=auth_svc.hash_password("Viewer!Pass1"),
        role_id=viewer_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def manager_user(db_session, manager_role) -> User:
    user = User(
        email="manager@example.com",
        full_name="Manager User",
        hashed_password=auth_svc.hash_password("Manager!Pass1"),
        role_id=manager_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── create user tests ─────────────────────────────────────────────────────────

async def test_create_user_sets_must_change_password(app_client, admin_user, viewer_role):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(
        "/api/v1/users",
        json={
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "NewUser!Pass1",
            "role_id": viewer_role.id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["must_change_password"] is True
    assert data["email"] == "newuser@example.com"


async def test_create_user_duplicate_email_returns_409(app_client, admin_user, viewer_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(
        "/api/v1/users",
        json={
            "email": "viewer@example.com",
            "full_name": "Duplicate",
            "password": "Duplicate!Pass1",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 409


async def test_create_user_weak_password_returns_422(app_client, admin_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(
        "/api/v1/users",
        json={
            "email": "weak@example.com",
            "full_name": "Weak",
            "password": "short",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ── deactivate / activate tests ───────────────────────────────────────────────

async def test_deactivate_user_blocks_login(app_client, admin_user, viewer_user, db_session):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")

    resp = await app_client.post(
        f"/api/v1/users/{viewer_user.id}/deactivate",
        headers=_auth(token),
    )
    assert resp.status_code == 204

    await db_session.refresh(viewer_user)
    assert viewer_user.is_active is False

    login_resp = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "Viewer!Pass1"},
    )
    assert login_resp.status_code == 401


async def test_activate_user_restores_access(app_client, admin_user, viewer_user, db_session):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")

    await app_client.post(f"/api/v1/users/{viewer_user.id}/deactivate", headers=_auth(token))
    resp = await app_client.post(f"/api/v1/users/{viewer_user.id}/activate", headers=_auth(token))
    assert resp.status_code == 204

    await db_session.refresh(viewer_user)
    assert viewer_user.is_active is True

    login_resp = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "Viewer!Pass1"},
    )
    assert login_resp.status_code == 200


# ── GDPR anonymisation tests ──────────────────────────────────────────────────

async def test_anonymise_user_replaces_pii(app_client, admin_user, viewer_user, db_session):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")

    resp = await app_client.delete(f"/api/v1/users/{viewer_user.id}", headers=_auth(token))
    assert resp.status_code == 204

    await db_session.refresh(viewer_user)
    assert viewer_user.full_name == "Deleted User"
    assert viewer_user.email.endswith("@deleted.local")
    assert viewer_user.hashed_password == "!ANONYMISED!"
    assert viewer_user.is_active is False
    assert viewer_user.anonymised_at is not None


async def test_anonymise_user_blocks_login(app_client, admin_user, viewer_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")

    await app_client.delete(f"/api/v1/users/{viewer_user.id}", headers=_auth(token))

    login_resp = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "Viewer!Pass1"},
    )
    assert login_resp.status_code == 401


async def test_anonymise_user_preserves_id(app_client, admin_user, viewer_user, db_session):
    """Referential integrity must hold — user row must still exist after anonymisation."""
    original_id = viewer_user.id
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    await app_client.delete(f"/api/v1/users/{viewer_user.id}", headers=_auth(token))

    await db_session.refresh(viewer_user)
    assert viewer_user.id == original_id


# ── permission matrix tests ───────────────────────────────────────────────────

async def test_viewer_cannot_manage_roles(app_client, viewer_user):
    token = await _login(app_client, "viewer@example.com", "Viewer!Pass1")
    # roles:manage permission required
    resp = await app_client.get("/api/v1/roles", headers=_auth(token))
    assert resp.status_code == 403


async def test_viewer_cannot_manage_users(app_client, viewer_user):
    token = await _login(app_client, "viewer@example.com", "Viewer!Pass1")
    resp = await app_client.get("/api/v1/users", headers=_auth(token))
    assert resp.status_code == 403


async def test_unauthenticated_request_returns_401(app_client):
    resp = await app_client.get("/api/v1/users")
    assert resp.status_code == 401


# ── role assignment guard tests ────────────────────────────────────────────────

async def test_manager_cannot_assign_superadmin_role(
    app_client, manager_user, viewer_user, superadmin_role
):
    token = await _login(app_client, "manager@example.com", "Manager!Pass1")
    resp = await app_client.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"role_id": superadmin_role.id},
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_admin_with_system_admin_can_assign_superadmin(
    app_client, admin_user, viewer_user, superadmin_role, db_session
):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"role_id": superadmin_role.id},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    await db_session.refresh(viewer_user)
    assert viewer_user.role_id == superadmin_role.id


# ── unlock tests ──────────────────────────────────────────────────────────────

async def test_unlock_user_resets_failed_count(app_client, admin_user, viewer_user, db_session):
    viewer_user.failed_login_count = 5
    await db_session.flush()

    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(f"/api/v1/users/{viewer_user.id}/unlock", headers=_auth(token))
    assert resp.status_code == 204

    await db_session.refresh(viewer_user)
    assert viewer_user.failed_login_count == 0
    assert viewer_user.locked_until is None


# ── role CRUD tests ───────────────────────────────────────────────────────────

async def test_list_roles(app_client, admin_user, viewer_role):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.get("/api/v1/roles", headers=_auth(token))
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "viewer" in names


async def test_create_role(app_client, admin_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(
        "/api/v1/roles",
        json={"name": "operator", "display_name": "Operator", "permissions": ["cameras:view", "recordings:view"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "operator"
    assert data["is_system_role"] is False


async def test_cannot_modify_system_role(app_client, admin_user, viewer_role):
    viewer_role.is_system_role = True

    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.patch(
        f"/api/v1/roles/{viewer_role.id}",
        json={"display_name": "Changed"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


async def test_cannot_delete_system_role(app_client, admin_user, admin_role):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.delete(f"/api/v1/roles/{admin_role.id}", headers=_auth(token))
    assert resp.status_code == 403


async def test_create_role_invalid_permission_returns_422(app_client, admin_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.post(
        "/api/v1/roles",
        json={"name": "bad_role", "permissions": ["nonexistent:permission"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ── sessions tests ────────────────────────────────────────────────────────────

async def test_list_user_sessions(app_client, admin_user, viewer_user, fake_redis):
    await _login(app_client, "viewer@example.com", "Viewer!Pass1")

    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.get(f"/api/v1/users/{viewer_user.id}/sessions", headers=_auth(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_revoke_all_sessions(app_client, admin_user, viewer_user, fake_redis, db_session):
    from sqlalchemy import select
    from app.models.session import UserSession

    await _login(app_client, "viewer@example.com", "Viewer!Pass1")

    admin_token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.delete(
        f"/api/v1/users/{viewer_user.id}/sessions", headers=_auth(admin_token)
    )
    assert resp.status_code == 204

    result = await db_session.execute(
        select(UserSession).where(UserSession.user_id == viewer_user.id)
    )
    sessions = result.scalars().all()
    assert len(sessions) > 0
    assert all(s.is_revoked for s in sessions)


# ── audit log tests ───────────────────────────────────────────────────────────

async def test_get_permissions_list(app_client, admin_user):
    token = await _login(app_client, "admin@example.com", "Admin!Pass1")
    resp = await app_client.get("/api/v1/roles/permissions", headers=_auth(token))
    assert resp.status_code == 200
    perms = resp.json()
    assert len(perms) > 0
    assert all("permission" in p and "category" in p for p in perms)
