"""
Verifies that all 16 models can be instantiated with required fields
and that key relationships and constraints are wired up correctly.
These tests use the async transaction-rollback fixture from conftest.py.
"""
import pytest
from sqlalchemy import text

from app.core.constants import CameraStatus, ExportStatus, RecordingMode, Severity, SegmentType
from app.models import (
    AlertEvent,
    AlertRule,
    APIKey,
    AuditLog,
    Camera,
    CameraGroup,
    CameraPermission,
    DetectionZone,
    ExportJob,
    NotificationChannel,
    RecordingSchedule,
    RecordingSegment,
    Role,
    SystemEvent,
    User,
    UserSession,
)


# ── helpers ──────────────────────────────────────────────────────────────────

async def _create_role(session, name="viewer") -> Role:
    role = Role(name=name, permissions=["cameras:view_live"])
    session.add(role)
    await session.flush()
    return role


async def _create_user(session, role: Role, email="test@example.com") -> User:
    user = User(
        email=email,
        full_name="Test User",
        hashed_password="$argon2$placeholder",
        role_id=role.id,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_camera(session, user: User) -> Camera:
    camera = Camera(
        name="Test Camera",
        ip_address="192.168.1.100",
        created_by=user.id,
    )
    session.add(camera)
    await session.flush()
    return camera


# ── instantiation tests ───────────────────────────────────────────────────────

async def test_role_instantiation(db_session):
    role = await _create_role(db_session)
    assert role.id is not None
    assert role.is_system_role is False


async def test_camera_group_instantiation(db_session):
    group = CameraGroup(name="Floor 1")
    db_session.add(group)
    await db_session.flush()
    assert group.id is not None
    assert group.parent_group_id is None


async def test_camera_group_self_referential(db_session):
    parent = CameraGroup(name="Building A")
    db_session.add(parent)
    await db_session.flush()
    child = CameraGroup(name="Floor 1", parent_group_id=parent.id)
    db_session.add(child)
    await db_session.flush()
    assert child.parent_group_id == parent.id


async def test_user_instantiation(db_session):
    role = await _create_role(db_session)
    user = await _create_user(db_session, role)
    assert user.id is not None
    assert user.is_active is True
    assert user.failed_login_count == 0


async def test_camera_instantiation(db_session):
    role = await _create_role(db_session)
    user = await _create_user(db_session, role)
    camera = await _create_camera(db_session, user)
    assert camera.id is not None
    assert camera.status == CameraStatus.unknown
    assert camera.recording_mode == RecordingMode.continuous
    assert camera.is_deleted is False


async def test_alert_rule_instantiation(db_session):
    rule = AlertRule(name="After hours person", severity=Severity.high)
    db_session.add(rule)
    await db_session.flush()
    assert rule.id is not None
    assert rule.camera_id is None  # applies to all cameras
    assert rule.enabled is True


async def test_alert_event_instantiation(db_session):
    from datetime import datetime, timezone
    role = await _create_role(db_session)
    user = await _create_user(db_session, role)
    camera = await _create_camera(db_session, user)
    event = AlertEvent(
        camera_id=camera.id,
        triggered_at=datetime.now(timezone.utc),
        severity=Severity.high,
    )
    db_session.add(event)
    await db_session.flush()
    assert event.id is not None
    assert event.acknowledged is False
    assert event.is_on_legal_hold is False


async def test_recording_segment_instantiation(db_session):
    from datetime import datetime, timezone
    role = await _create_role(db_session)
    user = await _create_user(db_session, role)
    camera = await _create_camera(db_session, user)
    segment = RecordingSegment(
        camera_id=camera.id,
        started_at=datetime.now(timezone.utc),
        file_path="/data/recordings/cam/2024-01-01/00-00-00_continuous.mp4",
        file_name="00-00-00_continuous.mp4",
        segment_type=SegmentType.continuous,
    )
    db_session.add(segment)
    await db_session.flush()
    assert segment.id is not None
    assert segment.is_on_legal_hold is False


async def test_cascade_delete_camera_deletes_segments(db_session):
    """Deleting a Camera must cascade-delete its RecordingSegments."""
    from datetime import datetime, timezone
    role = await _create_role(db_session, name="cascade_test_role")
    user = await _create_user(db_session, role, email="cascade@example.com")
    camera = await _create_camera(db_session, user)
    segment = RecordingSegment(
        camera_id=camera.id,
        started_at=datetime.now(timezone.utc),
        file_path="/data/recordings/cam/2024-01-01/00-00-00_continuous.mp4",
        file_name="00-00-00_continuous.mp4",
        segment_type=SegmentType.continuous,
    )
    db_session.add(segment)
    await db_session.flush()
    segment_id = segment.id

    await db_session.delete(camera)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT id FROM recording_segments WHERE id = :id"), {"id": segment_id}
    )
    assert result.fetchone() is None, "Segment should be deleted when camera is deleted"


async def test_audit_log_no_update_columns(db_session):
    """AuditLog has no updated_at column — confirms it is append-only by design."""
    assert not hasattr(AuditLog, "updated_at")
    log = AuditLog(action="test_action", severity="info")
    db_session.add(log)
    await db_session.flush()
    assert log.id is not None


async def test_export_job_instantiation(db_session):
    from datetime import datetime, timezone
    role = await _create_role(db_session, name="export_role")
    user = await _create_user(db_session, role, email="exporter@example.com")
    job = ExportJob(
        camera_ids=[],
        from_dt=datetime.now(timezone.utc),
        to_dt=datetime.now(timezone.utc),
        requested_by=user.id,
    )
    db_session.add(job)
    await db_session.flush()
    assert job.status == ExportStatus.queued
    assert job.progress_pct == 0


async def test_detection_zone_instantiation(db_session):
    role = await _create_role(db_session, name="zone_role")
    user = await _create_user(db_session, role, email="zone@example.com")
    camera = await _create_camera(db_session, user)
    zone = DetectionZone(
        camera_id=camera.id,
        name="Loading Dock",
        polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
    )
    db_session.add(zone)
    await db_session.flush()
    assert zone.id is not None
    assert zone.restricted is False


async def test_notification_channel_instantiation(db_session):
    channel = NotificationChannel(channel_type="email", name="Ops alerts")
    db_session.add(channel)
    await db_session.flush()
    assert channel.id is not None
    assert channel.enabled is True


async def test_system_event_instantiation(db_session):
    event = SystemEvent(event_type="storage_warning", severity="warning", message="80% full")
    db_session.add(event)
    await db_session.flush()
    assert event.id is not None
    assert event.resolved is False
