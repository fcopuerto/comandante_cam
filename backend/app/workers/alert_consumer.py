"""
Alert consumer and clip-saving Celery tasks.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.models.alert_event import AlertEvent
from app.models.camera import Camera
from app.models.notification_channel import NotificationChannel
from app.models.recording_segment import RecordingSegment

logger = structlog.get_logger(__name__)

_sync_engine = None
_SyncSession = None


def _get_session():
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        settings = get_settings()
        _sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=3, pool_pre_ping=True)
        _SyncSession = sessionmaker(bind=_sync_engine, expire_on_commit=False)
    return _SyncSession()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@celery_app.task(name="nvr.consume_alerts")
def consume_alerts() -> None:
    """Long-running task: subscribe to Redis nvr:alerts channel and process events."""
    import redis as sync_redis
    from app.schemas.alert import DetectionEvent

    settings = get_settings()
    r = sync_redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe("nvr:alerts")
    logger.info("alert_consumer_started")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            event = DetectionEvent.model_validate(data)
        except Exception as exc:
            logger.warning("alert_consumer_malformed_event", error=str(exc))
            continue

        db = _get_session()
        try:
            _process_detection_event(db, event)
            db.commit()
        except Exception:
            logger.exception("alert_consumer_process_error", camera_id=getattr(event, "camera_id", None))
            db.rollback()
        finally:
            db.close()


def _process_detection_event(db, event) -> None:
    """Sync version of alert_service.create_alert_from_detection for Celery context."""
    from app.core.constants import Severity
    from app.models.alert_rule import AlertRule
    from sqlalchemy import or_

    rules = db.execute(
        select(AlertRule)
        .where(
            AlertRule.enabled.is_(True),
            or_(AlertRule.camera_id == event.camera_id, AlertRule.camera_id.is_(None)),
        )
        .order_by(AlertRule.camera_id.nullslast(), AlertRule.created_at)
    ).scalars().all()

    matched_rule = None
    for rule in rules:
        if rule.detection_types and event.detection_type not in rule.detection_types:
            continue
        matched_rule = rule
        break

    severity = matched_rule.severity if matched_rule else event.severity
    rule_name = matched_rule.name if matched_rule else event.rule_triggered

    alert = AlertEvent(
        camera_id=event.camera_id,
        alert_rule_id=matched_rule.id if matched_rule else None,
        triggered_at=event.triggered_at,
        detection_type=event.detection_type,
        zone_name=event.zone_name,
        confidence=event.confidence,
        severity=severity,
        rule_triggered=rule_name,
        bbox=event.bbox,
        track_id=event.track_id,
        frame_path=event.frame_path,
    )
    db.add(alert)
    db.flush()

    save_alert_clip.delay(alert.id)
    send_alert_notifications_task.delay(alert.id)

    logger.info("alert_created_from_consumer", alert_id=alert.id, camera_id=event.camera_id)


@celery_app.task(name="nvr.save_alert_clip")
def save_alert_clip(alert_id: str) -> None:
    """Find the recording segment at triggered_at and clip ±30 seconds."""
    settings = get_settings()
    db = _get_session()
    try:
        alert = db.get(AlertEvent, alert_id)
        if not alert:
            logger.error("save_alert_clip_not_found", alert_id=alert_id)
            return

        # Find segment that contains triggered_at
        segment = db.execute(
            select(RecordingSegment)
            .where(
                RecordingSegment.camera_id == alert.camera_id,
                RecordingSegment.started_at <= alert.triggered_at,
                RecordingSegment.ended_at >= alert.triggered_at,
                RecordingSegment.is_corrupt.is_(False),
            )
            .order_by(RecordingSegment.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not segment or not segment.file_path:
            logger.warning("save_alert_clip_no_segment", alert_id=alert_id,
                           triggered_at=alert.triggered_at.isoformat())
            return

        source_path = Path(segment.file_path)
        if not source_path.exists():
            logger.warning("save_alert_clip_file_missing", alert_id=alert_id, path=str(source_path))
            return

        # Calculate offsets within the source file
        clip_start = max(alert.triggered_at - timedelta(seconds=30), segment.started_at)
        clip_end = min(alert.triggered_at + timedelta(seconds=30), segment.ended_at)
        start_offset = (clip_start - segment.started_at).total_seconds()
        duration = (clip_end - clip_start).total_seconds()
        if duration <= 0:
            return

        # Create output path
        clip_dir = settings.ALERT_CLIPS_PATH / alert_id
        clip_dir.mkdir(parents=True, exist_ok=True)
        clip_path = clip_dir / "clip.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_offset),
            "-i", str(source_path),
            "-t", str(duration),
            "-c", "copy",
            str(clip_path),
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            logger.error("save_alert_clip_ffmpeg_failed", alert_id=alert_id,
                         returncode=result.returncode)
            return

        if not clip_path.exists():
            return

        checksum = _sha256(clip_path)
        alert.clip_path = str(clip_path)
        alert.clip_checksum = checksum
        db.commit()

        logger.info("save_alert_clip_done", alert_id=alert_id, clip=str(clip_path))

    except Exception:
        logger.exception("save_alert_clip_error", alert_id=alert_id)
        db.rollback()
    finally:
        db.close()


@celery_app.task(name="nvr.send_alert_notifications")
def send_alert_notifications_task(alert_id: str) -> None:
    """Load alert + channels and dispatch notifications."""
    from app.services.notification_service import send_alert_notifications

    db = _get_session()
    try:
        alert = db.get(AlertEvent, alert_id)
        if not alert:
            return

        camera = db.get(Camera, alert.camera_id)
        if not camera:
            return

        # Find channels from matching rule
        rule_channel_ids: list[str] = []
        if alert.alert_rule_id:
            from app.models.alert_rule import AlertRule
            rule = db.get(AlertRule, alert.alert_rule_id)
            if rule:
                rule_channel_ids = list(rule.notification_channels or [])

        if not rule_channel_ids:
            return

        channels = db.execute(
            select(NotificationChannel)
            .where(NotificationChannel.id.in_(rule_channel_ids))
        ).scalars().all()

        send_alert_notifications(alert, camera, list(channels))

    except Exception:
        logger.exception("send_alert_notifications_task_error", alert_id=alert_id)
    finally:
        db.close()
