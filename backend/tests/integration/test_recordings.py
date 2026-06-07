"""
Integration tests for Session 8: recordings timeline, clip retrieval, export.

Run with: docker compose exec backend pytest tests/integration/test_recordings.py -v
"""
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport

import app.services.auth_service as auth_svc
from app.database import get_db
from app.main import create_app
from app.models.camera import Camera
from app.models.export_job import ExportJob
from app.models.recording_segment import RecordingSegment
from app.models.role import Role
from app.models.user import User
from app.redis_client import get_redis
from app.core.constants import ExportStatus, SegmentType


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def viewer_role(db_session) -> Role:
    role = Role(
        name="viewer_rec",
        permissions=["recordings:view", "recordings:export", "recordings:delete"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def other_role(db_session) -> Role:
    role = Role(name="other_rec", permissions=["cameras:view"], is_system_role=False)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def viewer_user(db_session, viewer_role) -> User:
    user = User(
        email="viewer_rec@example.com",
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
async def other_user(db_session, other_role) -> User:
    user = User(
        email="other_rec@example.com",
        full_name="Other",
        hashed_password=auth_svc.hash_password("Other!Pass1"),
        role_id=other_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_camera(db_session) -> Camera:
    camera = Camera(
        name="Rec Test Camera",
        ip_address="192.168.1.200",
        rtsp_main_url="rtsp://192.168.1.200/stream1",
        is_deleted=False,
    )
    db_session.add(camera)
    await db_session.flush()
    return camera


def _make_segment(camera_id: str, start: datetime, duration_s: int = 600,
                  segment_type=SegmentType.continuous, has_alert=False) -> RecordingSegment:
    end = start + timedelta(seconds=duration_s)
    return RecordingSegment(
        camera_id=camera_id,
        started_at=start,
        ended_at=end,
        duration_seconds=duration_s,
        file_path=f"/data/recordings/{camera_id}/segment.mp4",
        file_name="segment.mp4",
        file_size_bytes=50_000_000,
        segment_type=segment_type,
        has_alert=has_alert,
    )


@pytest_asyncio.fixture
async def segments(db_session, test_camera) -> list[RecordingSegment]:
    base = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    segs = [
        _make_segment(test_camera.id, base + timedelta(hours=i))
        for i in range(4)
    ]
    for s in segs:
        db_session.add(s)
    await db_session.flush()
    return segs


@pytest_asyncio.fixture
async def rec_client(db_session, fake_redis):
    application = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_redis] = override_redis

    from app.services.hls_service import HLSStreamManager
    application.state.hls_manager = MagicMock(spec=HLSStreamManager)

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        yield client


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── timeline tests ────────────────────────────────────────────────────────────

async def test_timeline_returns_segments(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(
        "/api/v1/recordings/timeline",
        params={"camera_id": test_camera.id, "date": "2025-06-01", "tz": "UTC"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_id"] == test_camera.id
    assert len(data["segments"]) == 4
    assert data["coverage_pct"] > 0


async def test_timeline_includes_gaps(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(
        "/api/v1/recordings/timeline",
        params={"camera_id": test_camera.id, "date": "2025-06-01"},
        headers=_auth(token),
    )
    data = resp.json()
    # 4 segments of 1h each starting at 00:00 → no gaps within 00:00-04:00, but gap after 04:00
    assert len(data["gaps"]) >= 1


async def test_timeline_empty_date_returns_full_gap(rec_client, viewer_user, test_camera):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(
        "/api/v1/recordings/timeline",
        params={"camera_id": test_camera.id, "date": "2020-01-01"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["segments"]) == 0
    assert len(data["gaps"]) == 1
    assert data["coverage_pct"] == 0


async def test_timeline_requires_auth(rec_client, test_camera):
    resp = await rec_client.get(
        "/api/v1/recordings/timeline",
        params={"camera_id": test_camera.id, "date": "2025-06-01"},
    )
    assert resp.status_code == 401


# ── calendar tests ────────────────────────────────────────────────────────────

async def test_calendar_returns_correct_coverage(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(
        "/api/v1/recordings/calendar",
        params={"camera_id": test_camera.id, "year": 2025, "month": 6},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_id"] == test_camera.id
    assert len(data["days"]) == 30

    june1 = next(d for d in data["days"] if d["date"] == "2025-06-01")
    assert june1["has_recordings"] is True
    assert june1["recording_hours"] > 0

    june2 = next(d for d in data["days"] if d["date"] == "2025-06-02")
    assert june2["has_recordings"] is False


# ── segments list tests ───────────────────────────────────────────────────────

async def test_list_segments_paginated(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(
        "/api/v1/recordings/segments",
        params={"camera_id": test_camera.id, "page": 1, "page_size": 2},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["pages"] == 2


async def test_get_segment_by_id(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    seg_id = segments[0].id
    resp = await rec_client.get(f"/api/v1/recordings/segments/{seg_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == seg_id


async def test_get_segment_invalid_id_returns_404(rec_client, viewer_user):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get("/api/v1/recordings/segments/not-a-uuid", headers=_auth(token))
    assert resp.status_code == 404


async def test_delete_segment_on_legal_hold_forbidden(rec_client, viewer_user, db_session, test_camera):
    seg = _make_segment(test_camera.id, datetime(2025, 5, 1, tzinfo=timezone.utc))
    seg.is_on_legal_hold = True
    db_session.add(seg)
    await db_session.flush()

    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.delete(f"/api/v1/recordings/segments/{seg.id}", headers=_auth(token))
    assert resp.status_code == 403


async def test_delete_segment_removes_row(rec_client, viewer_user, db_session, test_camera):
    seg = _make_segment(test_camera.id, datetime(2025, 4, 1, tzinfo=timezone.utc))
    db_session.add(seg)
    await db_session.flush()
    seg_id = seg.id

    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    with patch("pathlib.Path.exists", return_value=False):
        resp = await rec_client.delete(f"/api/v1/recordings/segments/{seg_id}", headers=_auth(token))
    assert resp.status_code == 204


# ── export tests ──────────────────────────────────────────────────────────────

async def test_create_export_job(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")

    with patch("app.workers.export.export_clip") as mock_task:
        mock_task.delay = MagicMock()
        resp = await rec_client.post(
            "/api/v1/exports",
            json={
                "camera_ids": [test_camera.id],
                "from_dt": "2025-06-01T00:00:00Z",
                "to_dt": "2025-06-01T02:00:00Z",
                "watermark": True,
            },
            headers=_auth(token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert data["camera_ids"] == [test_camera.id]
    assert data["estimated_size_bytes"] is not None


async def test_create_export_from_after_to_returns_422(rec_client, viewer_user, test_camera):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.post(
        "/api/v1/exports",
        json={
            "camera_ids": [test_camera.id],
            "from_dt": "2025-06-01T02:00:00Z",
            "to_dt": "2025-06-01T01:00:00Z",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_create_export_exceeds_4_hours_returns_422(rec_client, viewer_user, test_camera, segments):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.post(
        "/api/v1/exports",
        json={
            "camera_ids": [test_camera.id],
            "from_dt": "2025-06-01T00:00:00Z",
            "to_dt": "2025-06-01T05:00:00Z",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_create_export_no_segments_returns_422(rec_client, viewer_user, test_camera):
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.post(
        "/api/v1/exports",
        json={
            "camera_ids": [test_camera.id],
            "from_dt": "2020-01-01T00:00:00Z",
            "to_dt": "2020-01-01T01:00:00Z",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_export_status_poll(rec_client, viewer_user, db_session, test_camera):
    job = ExportJob(
        camera_ids=[test_camera.id],
        from_dt=datetime(2025, 6, 1, tzinfo=timezone.utc),
        to_dt=datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        status=ExportStatus.processing,
        progress_pct=42,
        requested_by=viewer_user.id,
    )
    db_session.add(job)
    await db_session.flush()

    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(f"/api/v1/exports/{job.id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert data["progress_pct"] == 42


async def test_export_download_streams_file(rec_client, viewer_user, db_session, test_camera, tmp_path):
    # Create a fake export file
    export_file = tmp_path / "export.mp4"
    export_file.write_bytes(b"fake video content")

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    job = ExportJob(
        camera_ids=[test_camera.id],
        from_dt=datetime(2025, 6, 1, tzinfo=timezone.utc),
        to_dt=datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        status=ExportStatus.completed,
        progress_pct=100,
        file_path=str(export_file),
        file_size_bytes=len(b"fake video content"),
        checksum_sha256="abc123",
        expires_at=expires,
        requested_by=viewer_user.id,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(f"/api/v1/exports/{job.id}/download", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.content == b"fake video content"
    assert "attachment" in resp.headers.get("content-disposition", "")


async def test_user_cannot_download_other_users_export(
    rec_client, viewer_user, other_user, db_session, test_camera
):
    """User cannot download another user's export."""
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    job = ExportJob(
        camera_ids=[test_camera.id],
        from_dt=datetime(2025, 6, 1, tzinfo=timezone.utc),
        to_dt=datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        status=ExportStatus.completed,
        progress_pct=100,
        file_path="/data/exports/fake.mp4",
        expires_at=expires,
        requested_by=other_user.id,  # owned by other_user
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    # viewer_user tries to download other_user's export
    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(f"/api/v1/exports/{job.id}/download", headers=_auth(token))
    assert resp.status_code == 403


async def test_export_download_expired_returns_422(rec_client, viewer_user, db_session, test_camera):
    expires = datetime.now(timezone.utc) - timedelta(hours=1)  # expired
    job = ExportJob(
        camera_ids=[test_camera.id],
        from_dt=datetime(2025, 6, 1, tzinfo=timezone.utc),
        to_dt=datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        status=ExportStatus.completed,
        progress_pct=100,
        file_path="/data/exports/old.mp4",
        expires_at=expires,
        requested_by=viewer_user.id,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    token = await _login(rec_client, "viewer_rec@example.com", "Viewer!Pass1")
    resp = await rec_client.get(f"/api/v1/exports/{job.id}/download", headers=_auth(token))
    assert resp.status_code == 422


async def test_export_requires_permission(rec_client, other_user):
    """User without recordings:export permission cannot create exports."""
    token = await _login(rec_client, "other_rec@example.com", "Other!Pass1")
    resp = await rec_client.post(
        "/api/v1/exports",
        json={"camera_ids": ["fake-id"], "from_dt": "2025-06-01T00:00:00Z", "to_dt": "2025-06-01T01:00:00Z"},
        headers=_auth(token),
    )
    assert resp.status_code == 403
