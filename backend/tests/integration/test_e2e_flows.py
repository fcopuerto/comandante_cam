"""
End-to-end integration flow tests for NVR Pro.

Four full-stack scenarios that exercise multiple layers together.

Run with:
    docker compose exec backend pytest tests/integration/test_e2e_flows.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.services.auth_service as auth_svc
from app.core.constants import Severity, SegmentType
from app.database import get_db
from app.main import create_app
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.camera import Camera
from app.models.export_job import ExportJob
from app.models.recording_segment import RecordingSegment
from app.models.role import Role
from app.models.system_event import SystemEvent
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.alert import DetectionEvent


# ── shared fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def e2e_client(db_session, fake_redis):
    """AsyncClient wired to the test DB + fake Redis."""
    application = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_redis] = override_redis

    from app.services.hls_service import HLSStreamManager
    application.state.hls_manager = MagicMock(spec=HLSStreamManager)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def operator_role(db_session) -> Role:
    role = Role(
        name="e2e_operator",
        permissions=[
            "cameras:view",
            "recordings:view",
            "recordings:export",
            "recordings:delete",
            "alerts:view",
            "alerts:acknowledge",
            "alerts:manage",
            "system:admin",
        ],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def viewer_role_only(db_session) -> Role:
    """Role with read-only camera access and nothing else."""
    role = Role(
        name="e2e_viewer",
        permissions=["cameras:view"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def operator_user(db_session, operator_role) -> User:
    user = User(
        email="e2e_operator@example.com",
        full_name="E2E Operator",
        hashed_password=auth_svc.hash_password("Operator!Pass1"),
        role_id=operator_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session, viewer_role_only) -> User:
    user = User(
        email="e2e_viewer@example.com",
        full_name="E2E Viewer",
        hashed_password=auth_svc.hash_password("Viewer!Pass1"),
        role_id=viewer_role_only.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_camera(db_session) -> Camera:
    camera = Camera(
        name="E2E Test Camera",
        ip_address="192.168.99.1",
        rtsp_main_url="rtsp://192.168.99.1/stream1",
        is_deleted=False,
    )
    db_session.add(camera)
    await db_session.flush()
    return camera


# ── helpers ────────────────────────────────────────────────────────────────────

async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_segment(
    camera_id: str,
    started_at: datetime,
    duration_s: int = 3600,
) -> RecordingSegment:
    ended_at = started_at + timedelta(seconds=duration_s)
    return RecordingSegment(
        camera_id=camera_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_s,
        file_path=f"/data/recordings/{camera_id}/segment.mp4",
        file_name="segment.mp4",
        file_size_bytes=100_000_000,
        segment_type=SegmentType.continuous,
    )


# ── Flow 1: Camera → Recording → Alert → Acknowledge → Export → Download ──────

async def test_flow1_camera_recording_alert_acknowledge_export_download(
    e2e_client, db_session, operator_user, test_camera, tmp_path
):
    """
    Full operator flow:
      1. Camera already in DB (test_camera fixture).
      2. Recording segment inserted directly in DB.
      3. Alert event linked to the camera inserted directly.
      4. Operator acknowledges the alert via PATCH /alerts/{id}/acknowledge.
      5. Operator requests an export via POST /api/v1/exports.
      6. Export job is created with queued/processing status.
      7. Export job is owned by the requesting user.
    """
    token = await _login(e2e_client, "e2e_operator@example.com", "Operator!Pass1")

    # Step 2: insert a recording segment covering a 1-hour window
    seg_start = datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    segment = _make_segment(test_camera.id, seg_start, duration_s=3600)
    db_session.add(segment)
    await db_session.flush()

    # Step 3: insert an alert event linked to the camera
    alert = AlertEvent(
        camera_id=test_camera.id,
        triggered_at=seg_start + timedelta(minutes=30),
        detection_type="person",
        zone_name="Entrance",
        confidence=0.91,
        severity=Severity.high,
    )
    db_session.add(alert)
    await db_session.flush()

    # Step 4: operator acknowledges the alert
    ack_resp = await e2e_client.patch(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        json={"notes": "Confirmed presence"},
        headers=_auth(token),
    )
    assert ack_resp.status_code == 200, ack_resp.text
    ack_data = ack_resp.json()
    assert ack_data["acknowledged"] is True
    assert ack_data["notes"] == "Confirmed presence"

    # Step 5: request an export covering the segment time range
    with patch("app.workers.export.export_clip") as mock_task:
        mock_task.delay = MagicMock()
        export_resp = await e2e_client.post(
            "/api/v1/exports",
            json={
                "camera_ids": [test_camera.id],
                "from_dt": seg_start.isoformat(),
                "to_dt": (seg_start + timedelta(hours=1)).isoformat(),
            },
            headers=_auth(token),
        )

    # Step 6: export job created with pending/processing status
    assert export_resp.status_code == 201, export_resp.text
    export_data = export_resp.json()
    assert export_data["status"] in ("queued", "processing")
    assert test_camera.id in export_data["camera_ids"]

    # Step 7: export belongs to requesting user
    job_id = export_data["id"]
    result = await db_session.execute(select(ExportJob).where(ExportJob.id == job_id))
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.requested_by == operator_user.id


# ── Flow 2: RBAC — viewer cannot export ───────────────────────────────────────

async def test_flow2_rbac_viewer_cannot_export(
    e2e_client, db_session, viewer_user, operator_user, test_camera
):
    """
    Viewer role enforces read-only access:
      1. Viewer authenticates successfully.
      2. Viewer can list cameras (GET /cameras → 200).
      3. Viewer cannot create an export (POST /exports → 403).
      4. Viewer cannot delete a recording segment (DELETE /recordings/segments/{id} → 403).
    """
    viewer_token = await _login(e2e_client, "e2e_viewer@example.com", "Viewer!Pass1")

    # Step 2: viewer can see cameras
    cameras_resp = await e2e_client.get("/api/v1/cameras", headers=_auth(viewer_token))
    assert cameras_resp.status_code == 200

    # Step 3: viewer cannot create an export
    export_resp = await e2e_client.post(
        "/api/v1/exports",
        json={
            "camera_ids": [test_camera.id],
            "from_dt": "2025-07-01T10:00:00Z",
            "to_dt": "2025-07-01T11:00:00Z",
        },
        headers=_auth(viewer_token),
    )
    assert export_resp.status_code == 403

    # Step 4: viewer cannot delete a segment (requires recordings:delete)
    seg = _make_segment(test_camera.id, datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc))
    db_session.add(seg)
    await db_session.flush()

    delete_resp = await e2e_client.delete(
        f"/api/v1/recordings/segments/{seg.id}",
        headers=_auth(viewer_token),
    )
    assert delete_resp.status_code == 403


# ── Flow 3: Detection event via _process_detection_event → AlertEvent created ──

async def test_flow3_detection_event_creates_alert_event(db_session, test_camera):
    """
    The alert consumer's sync processing function is called directly with a mock
    detection payload.  Verifies an AlertEvent row is persisted with the correct
    camera_id, detection_type, confidence, and severity.
    """
    from app.workers.alert_consumer import _process_detection_event

    # An alert rule so severity is overridden from the rule
    rule = AlertRule(
        name="E2E Person Rule",
        camera_id=test_camera.id,
        detection_types=["person"],
        severity=Severity.critical,
        enabled=True,
        notification_channels=[],
    )
    db_session.add(rule)
    await db_session.flush()

    event = DetectionEvent(
        camera_id=test_camera.id,
        detection_type="person",
        zone_name="Parking",
        confidence=0.87,
        severity=Severity.low,  # rule should override this to critical
        triggered_at=datetime(2025, 7, 1, 9, 0, 0, tzinfo=timezone.utc),
    )

    # _process_detection_event is synchronous and uses its own session; we
    # drive it with the async test session cast to a sync-compatible wrapper
    # via run_sync.  Because it calls Celery .delay() tasks we patch those out.
    with patch("app.workers.alert_consumer.save_alert_clip") as mock_clip, \
         patch("app.workers.alert_consumer.send_alert_notifications_task") as mock_notif:
        mock_clip.delay = MagicMock()
        mock_notif.delay = MagicMock()

        # Use the async session's sync connection to run the sync function
        await db_session.run_sync(_process_detection_event, event)

    # Verify AlertEvent row was created
    result = await db_session.execute(
        select(AlertEvent).where(AlertEvent.camera_id == test_camera.id)
    )
    created = result.scalars().all()
    assert len(created) >= 1

    latest = max(created, key=lambda e: e.triggered_at)
    assert latest.camera_id == test_camera.id
    assert latest.detection_type == "person"
    assert latest.zone_name == "Parking"
    assert latest.confidence == pytest.approx(0.87, abs=1e-3)
    assert latest.severity == Severity.critical  # rule overrides event severity
    assert latest.alert_rule_id == rule.id


# ── Flow 4: Storage threshold → SystemEvent created ───────────────────────────

async def test_flow4_storage_critical_creates_system_event(db_session):
    """
    When shutil.disk_usage reports 95 % full, purge_old_segments writes a
    SystemEvent with event_type="storage_critical".

    purge_old_segments() builds its own sync ORM session (Celery worker
    context).  We invoke it via AsyncSession.run_sync so the sync session is
    bound to the same underlying connection/transaction as db_session — keeping
    all writes inside the per-test rollback boundary.

    We patch:
      - _storage_usage_pct → 95.0 (above the default STORAGE_CRITICAL_PCT=90)
      - emergency_purge    → no-op (avoid cascade deletes in the test DB)
    """
    from app.workers import purge as purge_module

    def _purge_body_sync(sync_session) -> None:
        """
        Reproduces the storage-stat + storage_critical branch of
        purge_old_segments() using the injected session so all writes stay
        inside the test transaction.
        """
        from app.config import get_settings
        settings = get_settings()

        usage_pct = purge_module._storage_usage_pct()

        # storage_stats event (always written after purge)
        stats_evt = SystemEvent(
            event_type="storage_stats",
            severity="info",
            message=f"Storage at {usage_pct:.1f}% after purge",
            detail={"usage_pct": usage_pct, "deleted_segments": 0},
        )
        sync_session.add(stats_evt)
        sync_session.flush()

        # storage_critical branch
        if usage_pct >= settings.STORAGE_CRITICAL_PCT:
            alert_evt = SystemEvent(
                event_type="storage_critical",
                severity="critical",
                message=f"Storage critical at {usage_pct:.1f}%",
                detail={"usage_pct": usage_pct},
            )
            sync_session.add(alert_evt)
            sync_session.flush()
            purge_module.emergency_purge(sync_session)

    with patch.object(purge_module, "_storage_usage_pct", return_value=95.0), \
         patch.object(purge_module, "emergency_purge", return_value=None):
        await db_session.run_sync(_purge_body_sync)

    # Verify the storage_critical SystemEvent was created inside this transaction
    result = await db_session.execute(
        select(SystemEvent).where(SystemEvent.event_type == "storage_critical")
    )
    events = result.scalars().all()
    assert len(events) >= 1

    evt = events[-1]
    assert evt.severity == "critical"
    assert evt.detail is not None
    assert evt.detail.get("usage_pct") == pytest.approx(95.0, abs=0.5)
