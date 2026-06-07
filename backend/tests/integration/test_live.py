"""
Integration tests for Session 7: HLS streaming and WebSocket hub.

Run with: docker compose exec backend pytest tests/integration/test_live.py -v
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

import app.services.auth_service as auth_svc
from app.database import get_db
from app.main import create_app
from app.models.camera import Camera
from app.models.role import Role
from app.models.user import User
from app.redis_client import get_redis
from app.services.hls_service import HLSStreamManager


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def viewer_role(db_session) -> Role:
    role = Role(name="viewer_live", permissions=["cameras:view"], is_system_role=False)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def admin_role(db_session) -> Role:
    role = Role(
        name="admin_live",
        permissions=["cameras:manage", "cameras:view", "system:admin"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def viewer_user(db_session, viewer_role) -> User:
    user = User(
        email="viewer_live@example.com",
        full_name="Viewer",
        hashed_password=auth_svc.hash_password("Viewer!Pass1"),
        role_id=viewer_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session, admin_role) -> User:
    user = User(
        email="admin_live@example.com",
        full_name="Admin",
        hashed_password=auth_svc.hash_password("Admin!Pass1"),
        role_id=admin_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_camera(db_session) -> Camera:
    camera = Camera(
        name="Test Camera",
        ip_address="192.168.1.100",
        rtsp_main_url="rtsp://192.168.1.100/stream1",
        rtsp_sub_url="rtsp://192.168.1.100/stream2",
        is_deleted=False,
    )
    db_session.add(camera)
    await db_session.flush()
    return camera


@pytest_asyncio.fixture
async def mock_hls_manager():
    manager = MagicMock(spec=HLSStreamManager)
    manager.start_stream = AsyncMock(return_value="/hls/test-camera-id/index.m3u8")
    manager.stop_stream = AsyncMock()
    manager.get_status = AsyncMock(return_value={})
    manager.is_running = MagicMock(return_value=True)
    manager.add_viewer = MagicMock()
    manager.remove_viewer = MagicMock()
    manager.viewer_count = MagicMock(return_value=0)
    return manager


@pytest_asyncio.fixture
async def live_client(db_session, fake_redis, mock_hls_manager):
    application = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_redis] = override_redis
    application.state.hls_manager = mock_hls_manager

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        yield client, application


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── HLS stream-url tests ──────────────────────────────────────────────────────

async def test_stream_url_starts_hls_and_returns_url(live_client, viewer_user, test_camera):
    client, app = live_client
    mock_hls = app.state.hls_manager
    mock_hls.start_stream = AsyncMock(return_value=f"/hls/{test_camera.id}/index.m3u8")

    token = await _login(client, "viewer_live@example.com", "Viewer!Pass1")
    resp = await client.get(f"/api/v1/live/{test_camera.id}/stream-url", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "hls_url" in data
    assert f"/hls/{test_camera.id}/index.m3u8" in data["hls_url"]
    mock_hls.start_stream.assert_called_once()


async def test_stream_url_idempotent(live_client, viewer_user, test_camera):
    """Second call to stream-url returns same URL without restarting FFmpeg."""
    client, app = live_client
    mock_hls = app.state.hls_manager
    mock_hls.start_stream = AsyncMock(return_value=f"/hls/{test_camera.id}/index.m3u8")

    token = await _login(client, "viewer_live@example.com", "Viewer!Pass1")
    resp1 = await client.get(f"/api/v1/live/{test_camera.id}/stream-url", headers=_auth(token))
    resp2 = await client.get(f"/api/v1/live/{test_camera.id}/stream-url", headers=_auth(token))

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["hls_url"] == resp2.json()["hls_url"]
    assert mock_hls.start_stream.call_count == 2


async def test_stream_url_404_for_unknown_camera(live_client, viewer_user):
    client, _ = live_client
    token = await _login(client, "viewer_live@example.com", "Viewer!Pass1")
    resp = await client.get("/api/v1/live/nonexistent-id/stream-url", headers=_auth(token))
    assert resp.status_code == 404


async def test_stream_url_requires_auth(live_client, test_camera):
    client, _ = live_client
    resp = await client.get(f"/api/v1/live/{test_camera.id}/stream-url")
    assert resp.status_code == 401


async def test_force_stop_stream_requires_manage_permission(live_client, viewer_user, test_camera):
    client, _ = live_client
    token = await _login(client, "viewer_live@example.com", "Viewer!Pass1")
    resp = await client.delete(f"/api/v1/live/{test_camera.id}/stream", headers=_auth(token))
    assert resp.status_code == 403


async def test_force_stop_stream_admin(live_client, admin_user, test_camera):
    client, app = live_client
    mock_hls = app.state.hls_manager
    token = await _login(client, "admin_live@example.com", "Admin!Pass1")
    resp = await client.delete(f"/api/v1/live/{test_camera.id}/stream", headers=_auth(token))
    assert resp.status_code == 204
    mock_hls.stop_stream.assert_called_once_with(test_camera.id)


async def test_list_active_streams_admin_only(live_client, viewer_user, admin_user):
    client, app = live_client
    app.state.hls_manager.get_status = AsyncMock(return_value={"cam1": {"status": "running", "viewers": 1}})

    viewer_token = await _login(client, "viewer_live@example.com", "Viewer!Pass1")
    admin_token = await _login(client, "admin_live@example.com", "Admin!Pass1")

    resp_viewer = await client.get("/api/v1/live/active", headers=_auth(viewer_token))
    assert resp_viewer.status_code == 403

    resp_admin = await client.get("/api/v1/live/active", headers=_auth(admin_token))
    assert resp_admin.status_code == 200
    assert "streams" in resp_admin.json()


# ── HLSStreamManager unit tests ────────────────────────────────────────────────

async def test_hls_manager_start_stream_idempotent():
    manager = HLSStreamManager()
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = True

    camera = MagicMock()
    camera.id = "cam-123"
    camera.rtsp_sub_url = "rtsp://192.168.1.1/sub"
    camera.rtsp_main_url = "rtsp://192.168.1.1/main"

    with patch("app.services.hls_service.build_hls_command", return_value=["ffmpeg"]):
        with patch("app.services.hls_service.FFmpegProcess") as MockProc:
            MockProc.return_value = mock_proc
            with patch("asyncio.to_thread", new_callable=AsyncMock):
                with patch("pathlib.Path.mkdir"):
                    url1 = await manager.start_stream(camera)

    # Now proc is in _streams, mark it as running
    manager._streams["cam-123"] = mock_proc
    url2 = await manager.start_stream(camera)

    assert url1 == url2 == f"/hls/{camera.id}/index.m3u8"


async def test_hls_manager_viewer_tracking():
    manager = HLSStreamManager()
    manager._viewers["cam-1"] = set()

    manager.add_viewer("cam-1", "user-1")
    manager.add_viewer("cam-1", "user-2")
    assert manager.viewer_count("cam-1") == 2

    manager.remove_viewer("cam-1", "user-1")
    assert manager.viewer_count("cam-1") == 1

    manager.remove_viewer("cam-1", "user-2")
    assert manager.viewer_count("cam-1") == 0


async def test_hls_manager_stop_removes_from_dict():
    manager = HLSStreamManager()
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = True
    manager._streams["cam-x"] = mock_proc
    manager._viewers["cam-x"] = {"user-1"}

    with patch("asyncio.to_thread", new_callable=AsyncMock):
        with patch("pathlib.Path.exists", return_value=False):
            await manager.stop_stream("cam-x")

    assert "cam-x" not in manager._streams
    assert "cam-x" not in manager._viewers


# ── WebSocket authentication tests ───────────────────────────────────────────

def _make_mock_hls():
    mock_hls = MagicMock(spec=HLSStreamManager)
    mock_hls.add_viewer = MagicMock()
    mock_hls.remove_viewer = MagicMock()
    mock_hls.viewer_count = MagicMock(return_value=0)
    mock_hls.stop_stream = AsyncMock()
    return mock_hls


async def test_websocket_invalid_token_closes_with_4001():
    """Server closes with code 4001 when token is invalid."""
    from starlette.websockets import WebSocketDisconnect

    application = create_app()
    application.state.hls_manager = _make_mock_hls()

    with TestClient(application, raise_server_exceptions=False) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws?token=not-a-valid-jwt"):
                pass
        assert exc_info.value.code == 4001


async def test_websocket_valid_token_receives_initial_state(viewer_user):
    """Valid token → connection accepted → initial_state message sent."""
    token = auth_svc.create_access_token(
        user_id=viewer_user.id,
        email=viewer_user.email,
        role_name="viewer",
        permissions=["cameras:view"],
    )

    # Mock DB: returns the viewer_user on User lookup, empty results for initial state queries
    mock_user = MagicMock()
    mock_user.id = viewer_user.id
    mock_user.is_active = True

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = mock_user

    # For camera/alert queries in _get_initial_state, return empty
    empty_result = MagicMock()
    empty_result.all.return_value = []
    empty_result.scalar_one.return_value = 0

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [user_result, empty_result, empty_result]

    async def override_db():
        yield mock_session

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.state.hls_manager = _make_mock_hls()

    from unittest.mock import patch
    with patch("app.routers.ws._get_initial_state", new_callable=AsyncMock,
               return_value={"camera_statuses": {}, "unread_alerts": 0}):
        # base_url="http://test" → Host: test — matches ALLOWED_HOSTS from conftest
        with TestClient(application, raise_server_exceptions=False, base_url="http://test") as client:
            with client.websocket_connect(f"/ws?token={token}") as ws:
                data = ws.receive_json()
                assert data["type"] == "initial_state"
                assert "camera_statuses" in data
                assert "unread_alerts" in data
