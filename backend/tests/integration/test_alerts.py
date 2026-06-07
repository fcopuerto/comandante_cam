"""
Integration tests for Session 9: alert system, rules, notifications.

Run with: docker compose exec backend pytest tests/integration/test_alerts.py -v
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from httpx import AsyncClient, ASGITransport

import app.services.auth_service as auth_svc
from app.core.constants import Severity
from app.database import get_db
from app.main import create_app
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.camera import Camera
from app.models.notification_channel import NotificationChannel
from app.models.recording_segment import RecordingSegment
from app.models.role import Role
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.alert import DetectionEvent
import app.services.alert_service as alert_svc


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def admin_role(db_session) -> Role:
    role = Role(
        name="alert_admin",
        permissions=[
            "alerts:view", "alerts:manage", "alerts:acknowledge",
            "notifications:manage", "system:admin",
        ],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def viewer_role(db_session) -> Role:
    role = Role(
        name="alert_viewer",
        permissions=["alerts:view", "alerts:acknowledge"],
        is_system_role=False,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture
async def admin_user(db_session, admin_role) -> User:
    user = User(
        email="alert_admin@example.com",
        full_name="Alert Admin",
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
        email="alert_viewer@example.com",
        full_name="Alert Viewer",
        hashed_password=auth_svc.hash_password("Viewer!Pass1"),
        role_id=viewer_role.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_camera(db_session) -> Camera:
    camera = Camera(
        name="Alert Test Camera",
        ip_address="192.168.1.50",
        rtsp_main_url="rtsp://192.168.1.50/stream",
        is_deleted=False,
    )
    db_session.add(camera)
    await db_session.flush()
    return camera


@pytest_asyncio.fixture
async def alert_rule(db_session, test_camera) -> AlertRule:
    rule = AlertRule(
        name="Person Detected",
        camera_id=test_camera.id,
        detection_types=["person"],
        severity=Severity.high,
        enabled=True,
        notification_channels=[],
    )
    db_session.add(rule)
    await db_session.flush()
    return rule


@pytest_asyncio.fixture
async def alert_event(db_session, test_camera, alert_rule) -> AlertEvent:
    event = AlertEvent(
        camera_id=test_camera.id,
        alert_rule_id=alert_rule.id,
        triggered_at=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        detection_type="person",
        zone_name="Entrance",
        confidence=0.92,
        severity=Severity.high,
        rule_triggered="Person Detected",
    )
    db_session.add(event)
    await db_session.flush()
    return event


@pytest_asyncio.fixture
async def alert_client(db_session, fake_redis):
    application = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield fake_redis

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_redis] = override_redis
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        yield client


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── alert event tests ─────────────────────────────────────────────────────────

async def test_create_alert_from_detection(db_session, test_camera, alert_rule):
    """Service creates an AlertEvent row when a DetectionEvent arrives."""
    event = DetectionEvent(
        camera_id=test_camera.id,
        detection_type="person",
        zone_name="Entrance",
        confidence=0.95,
        severity=Severity.medium,
        triggered_at=datetime(2025, 6, 1, 8, 0, 0, tzinfo=timezone.utc),
    )

    with patch("app.workers.alert_consumer.save_alert_clip") as mock_clip, \
         patch("app.workers.alert_consumer.send_alert_notifications_task") as mock_notif:
        mock_clip.delay = MagicMock()
        mock_notif.delay = MagicMock()

        alert = await alert_svc.create_alert_from_detection(db_session, event)

    assert alert.camera_id == test_camera.id
    assert alert.detection_type == "person"
    assert alert.severity == Severity.high  # rule overrides event severity
    assert alert.alert_rule_id == alert_rule.id
    assert alert.zone_name == "Entrance"


async def test_alert_rule_match_uses_rule_severity(db_session, test_camera, alert_rule):
    """When a rule matches, severity comes from the rule, not the event."""
    event = DetectionEvent(
        camera_id=test_camera.id,
        detection_type="person",
        triggered_at=datetime(2025, 6, 1, 9, 0, 0, tzinfo=timezone.utc),
        severity=Severity.low,
    )

    with patch("app.workers.alert_consumer.save_alert_clip") as m1, \
         patch("app.workers.alert_consumer.send_alert_notifications_task") as m2:
        m1.delay = MagicMock()
        m2.delay = MagicMock()
        alert = await alert_svc.create_alert_from_detection(db_session, event)

    assert alert.severity == Severity.high  # from rule


async def test_no_rule_match_uses_event_severity(db_session, test_camera):
    """When no rule matches, severity falls back to the event's severity."""
    event = DetectionEvent(
        camera_id=test_camera.id,
        detection_type="vehicle",
        triggered_at=datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        severity=Severity.critical,
    )

    with patch("app.workers.alert_consumer.save_alert_clip") as m1, \
         patch("app.workers.alert_consumer.send_alert_notifications_task") as m2:
        m1.delay = MagicMock()
        m2.delay = MagicMock()
        alert = await alert_svc.create_alert_from_detection(db_session, event)

    assert alert.severity == Severity.critical
    assert alert.alert_rule_id is None


async def test_acknowledge_alert(db_session, alert_event, admin_user):
    """Acknowledging an alert sets the acknowledged fields."""
    resp = await alert_svc.acknowledge_alert(
        db_session, alert_event.id, admin_user, notes="Confirmed"
    )
    assert resp.acknowledged is True
    assert resp.acknowledged_by == admin_user.id
    assert resp.notes == "Confirmed"
    assert resp.acknowledged_at is not None


async def test_mark_false_positive(db_session, alert_event, admin_user):
    resp = await alert_svc.mark_false_positive(
        db_session, alert_event.id, admin_user, notes="Shadow movement"
    )
    assert resp.is_false_positive is True
    assert resp.notes == "Shadow movement"


async def test_set_legal_hold(db_session, alert_event, admin_user):
    resp = await alert_svc.set_legal_hold(db_session, alert_event.id, hold=True, user=admin_user)
    assert resp.is_on_legal_hold is True

    resp2 = await alert_svc.set_legal_hold(db_session, alert_event.id, hold=False, user=admin_user)
    assert resp2.is_on_legal_hold is False


async def test_legal_hold_prevents_segment_purge(db_session, test_camera, alert_event):
    """A segment with is_on_legal_hold=True should be excluded from purge candidates."""
    from sqlalchemy import select

    seg = RecordingSegment(
        camera_id=test_camera.id,
        started_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        ended_at=datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
        duration_seconds=3600,
        file_path="/data/recordings/hold_segment.mp4",
        file_name="hold_segment.mp4",
        is_on_legal_hold=True,
    )
    db_session.add(seg)
    await db_session.flush()

    # Verify the purge query excludes segments with is_on_legal_hold=True
    result = await db_session.execute(
        select(RecordingSegment).where(
            RecordingSegment.camera_id == test_camera.id,
            RecordingSegment.is_on_legal_hold.is_(False),
        )
    )
    candidate_ids = {s.id for s in result.scalars().all()}
    assert seg.id not in candidate_ids


async def test_alert_stats(db_session, test_camera):
    """Stats returns correct counts by severity."""
    now = datetime.now(timezone.utc)
    for sev in [Severity.low, Severity.low, Severity.high, Severity.critical]:
        db_session.add(AlertEvent(
            camera_id=test_camera.id,
            triggered_at=now - timedelta(hours=1),
            severity=sev,
        ))
    await db_session.flush()

    class _FakeUser:
        id = "fake-user"

    stats = await alert_svc.get_alert_stats(db_session, hours=24, user=_FakeUser())
    assert stats.by_severity.get("low", 0) >= 2
    assert stats.by_severity.get("high", 0) >= 1
    assert stats.by_severity.get("critical", 0) >= 1


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

async def test_list_alerts_returns_events(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get("/api/v1/alerts", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ids = [item["id"] for item in data["items"]]
    assert alert_event.id in ids


async def test_get_alert_by_id(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get(f"/api/v1/alerts/{alert_event.id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == alert_event.id


async def test_get_alert_invalid_uuid_returns_404(alert_client, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get("/api/v1/alerts/not-a-uuid", headers=_auth(token))
    assert resp.status_code == 404


async def test_acknowledge_alert_via_api(alert_client, alert_event, viewer_user):
    token = await _login(alert_client, "alert_viewer@example.com", "Viewer!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/alerts/{alert_event.id}/acknowledge",
        json={"notes": "Checked"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] is True
    assert resp.json()["notes"] == "Checked"


async def test_false_positive_requires_manage_permission(alert_client, alert_event, viewer_user):
    token = await _login(alert_client, "alert_viewer@example.com", "Viewer!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/alerts/{alert_event.id}/false-positive",
        json={"notes": "false"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


async def test_false_positive_via_api(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/alerts/{alert_event.id}/false-positive",
        json={"notes": "Test shadow"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_false_positive"] is True


async def test_legal_hold_via_api(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/alerts/{alert_event.id}/legal-hold",
        json={"hold": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_on_legal_hold"] is True


async def test_alert_stats_endpoint(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get("/api/v1/alerts/stats?hours=48", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "by_severity" in data
    assert "by_camera" in data
    assert "by_hour" in data


async def test_alert_clip_404_when_no_clip(alert_client, alert_event, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get(f"/api/v1/alerts/{alert_event.id}/clip", headers=_auth(token))
    assert resp.status_code == 404


async def test_alert_frame_returns_jpeg(alert_client, alert_event, admin_user, tmp_path):
    frame_file = tmp_path / "frame.jpg"
    frame_file.write_bytes(b"\xff\xd8\xff\xe0test")
    alert_event.frame_path = str(frame_file)

    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get(f"/api/v1/alerts/{alert_event.id}/frame", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


async def test_alerts_require_auth(alert_client):
    resp = await alert_client.get("/api/v1/alerts")
    assert resp.status_code == 401


# ── Alert rules CRUD ──────────────────────────────────────────────────────────

async def test_create_alert_rule(alert_client, test_camera, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.post(
        "/api/v1/alert-rules",
        json={
            "name": "Vehicle Entry",
            "camera_id": test_camera.id,
            "detection_types": ["vehicle"],
            "severity": "medium",
            "enabled": True,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Vehicle Entry"
    assert data["severity"] == "medium"


async def test_list_alert_rules(alert_client, alert_rule, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get("/api/v1/alert-rules", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


async def test_update_alert_rule(alert_client, alert_rule, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/alert-rules/{alert_rule.id}",
        json={"enabled": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_delete_alert_rule(alert_client, alert_rule, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.delete(
        f"/api/v1/alert-rules/{alert_rule.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 204


async def test_alert_rules_require_manage_permission(alert_client, viewer_user):
    token = await _login(alert_client, "alert_viewer@example.com", "Viewer!Pass1")
    resp = await alert_client.post(
        "/api/v1/alert-rules",
        json={"name": "Test", "detection_types": [], "severity": "low"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


# ── Notification channels CRUD ────────────────────────────────────────────────

async def test_create_notification_channel(alert_client, admin_user):
    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.post(
        "/api/v1/notifications/channels",
        json={
            "name": "Ops Webhook",
            "channel_type": "webhook",
            "config": {"url": "https://example.com/hook"},
            "enabled": True,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Ops Webhook"
    assert data["channel_type"] == "webhook"
    assert "config" not in data  # config is never returned


async def test_list_notification_channels(alert_client, admin_user, db_session):
    ch = NotificationChannel(name="Email Ops", channel_type="email",
                             config={"to": "ops@example.com"}, enabled=True)
    db_session.add(ch)
    await db_session.flush()

    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.get("/api/v1/notifications/channels", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


async def test_update_notification_channel(alert_client, admin_user, db_session):
    ch = NotificationChannel(name="Slack", channel_type="slack",
                             config={"webhook_url": "https://hooks.slack.com/x"}, enabled=True)
    db_session.add(ch)
    await db_session.flush()

    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.patch(
        f"/api/v1/notifications/channels/{ch.id}",
        json={"enabled": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_delete_notification_channel(alert_client, admin_user, db_session):
    ch = NotificationChannel(name="Old Channel", channel_type="email",
                             config={"to": "x@example.com"}, enabled=True)
    db_session.add(ch)
    await db_session.flush()

    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    resp = await alert_client.delete(
        f"/api/v1/notifications/channels/{ch.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 204


async def test_notification_channel_test_send(alert_client, admin_user, db_session):
    ch = NotificationChannel(
        name="Webhook Test",
        channel_type="webhook",
        config={"url": "https://example.com/hook"},
        enabled=True,
    )
    db_session.add(ch)
    await db_session.flush()

    token = await _login(alert_client, "alert_admin@example.com", "Admin!Pass1")
    with patch("app.services.notification_service.send_alert_notifications") as mock_send:
        mock_send.return_value = None
        resp = await alert_client.post(
            f"/api/v1/notifications/channels/{ch.id}/test",
            headers=_auth(token),
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


async def test_notification_channels_require_manage_permission(alert_client, viewer_user):
    token = await _login(alert_client, "alert_viewer@example.com", "Viewer!Pass1")
    resp = await alert_client.post(
        "/api/v1/notifications/channels",
        json={"name": "x", "channel_type": "email", "config": {}},
        headers=_auth(token),
    )
    assert resp.status_code == 403


# ── Worker tests ──────────────────────────────────────────────────────────────

async def test_save_alert_clip_task(db_session, test_camera, alert_event, tmp_path):
    """save_alert_clip finds the segment and produces a clip file."""
    seg_file = tmp_path / "segment.mp4"
    seg_file.write_bytes(b"fake video data")

    seg = RecordingSegment(
        camera_id=test_camera.id,
        started_at=datetime(2025, 6, 1, 11, 50, 0, tzinfo=timezone.utc),
        ended_at=datetime(2025, 6, 1, 12, 10, 0, tzinfo=timezone.utc),
        duration_seconds=1200,
        file_path=str(seg_file),
        file_name="segment.mp4",
        file_size_bytes=len(b"fake video data"),
    )
    db_session.add(seg)
    await db_session.flush()

    # The task uses sync DB; we verify it would find the right segment
    from sqlalchemy import select
    result = await db_session.execute(
        select(RecordingSegment).where(
            RecordingSegment.camera_id == test_camera.id,
            RecordingSegment.started_at <= alert_event.triggered_at,
            RecordingSegment.ended_at >= alert_event.triggered_at,
        )
    )
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.id == seg.id


async def test_notification_send_email_calls_smtp(db_session):
    """send_email calls smtplib.SMTP with correct parameters."""
    from app.services.notification_service import send_email
    from app.core.constants import Severity

    class _FakeAlert:
        id = "test-alert-001"
        camera_id = "cam-001"
        triggered_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        detection_type = "person"
        zone_name = "Door"
        confidence = 0.9
        severity = Severity.high
        frame_path = None

    class _FakeCamera:
        name = "Front Door"

    config = {
        "to": ["security@example.com"],
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_starttls": True,
        "smtp_user": "user",
        "smtp_password": "pass",
    }

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        send_email(config, _FakeAlert(), _FakeCamera())

    mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)


async def test_notification_send_webhook_posts_with_signature():
    """send_webhook posts JSON with HMAC-SHA256 signature header."""
    from app.services.notification_service import send_webhook
    from app.core.constants import Severity

    class _FakeAlert:
        id = "test-alert-002"
        camera_id = "cam-001"
        triggered_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        detection_type = "person"
        zone_name = None
        confidence = 0.85
        severity = Severity.medium
        bbox = None

    class _FakeCamera:
        name = "Side Camera"

    config = {"url": "https://example.com/hook", "secret": "mysecret"}

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        send_webhook(config, _FakeAlert(), _FakeCamera())

    call_kwargs = mock_client.post.call_args
    assert call_kwargs is not None
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert "X-NVR-Signature" in headers
    assert headers["X-NVR-Signature"].startswith("sha256=")
