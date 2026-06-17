"""
Alert service — creates events from detections, handles acknowledgement,
false-positive marking, legal hold, and stats.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit_service as audit_svc
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.camera import Camera
from app.models.user import User
from app.schemas.alert import (
    AlertEventResponse,
    AlertStatsResponse,
    DetectionEvent,
)

logger = structlog.get_logger(__name__)


def _alert_response(alert: AlertEvent) -> AlertEventResponse:
    return AlertEventResponse(
        id=alert.id,
        camera_id=alert.camera_id,
        alert_rule_id=alert.alert_rule_id,
        triggered_at=alert.triggered_at,
        detection_type=alert.detection_type,
        zone_name=alert.zone_name,
        confidence=alert.confidence,
        severity=alert.severity,
        rule_triggered=alert.rule_triggered,
        bbox=alert.bbox,
        track_id=alert.track_id,
        frame_path=alert.frame_path,
        clip_path=alert.clip_path,
        clip_checksum=alert.clip_checksum,
        is_false_positive=alert.is_false_positive,
        is_on_legal_hold=alert.is_on_legal_hold,
        acknowledged=alert.acknowledged,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        notes=alert.notes,
        created_at=alert.created_at,
    )


def _rule_matches_schedule(rule: AlertRule, when: datetime) -> bool:
    if not rule.schedule:
        return True
    from datetime import time as dt_time
    days = rule.schedule.get("days")
    time_start_str = rule.schedule.get("time_start")
    time_end_str = rule.schedule.get("time_end")
    if days is not None and when.weekday() not in days:
        return False
    if time_start_str and time_end_str:
        parts_s = time_start_str.split(":")
        parts_e = time_end_str.split(":")
        start = dt_time(int(parts_s[0]), int(parts_s[1]))
        end = dt_time(int(parts_e[0]), int(parts_e[1]))
        current = when.time()
        if start <= end:
            if not (start <= current <= end):
                return False
        else:
            if not (current >= start or current <= end):
                return False
    return True


async def _find_matching_rule(db: AsyncSession, event: DetectionEvent) -> AlertRule | None:
    result = await db.execute(
        select(AlertRule)
        .where(
            AlertRule.enabled.is_(True),
            or_(AlertRule.camera_id == event.camera_id, AlertRule.camera_id.is_(None)),
        )
        .order_by(AlertRule.camera_id.nullslast(), AlertRule.created_at)
    )
    rules = result.scalars().all()

    for rule in rules:
        if rule.detection_types and event.detection_type not in rule.detection_types:
            continue
        if not _rule_matches_schedule(rule, event.triggered_at):
            continue
        return rule
    return None


async def create_alert_from_detection(
    db: AsyncSession,
    event: DetectionEvent,
) -> AlertEvent:
    rule = await _find_matching_rule(db, event)

    severity = rule.severity if rule else event.severity
    rule_name = rule.name if rule else event.rule_triggered

    # Save base64 frame to disk if no frame_path given
    frame_path = event.frame_path
    if not frame_path and event.frame_b64:
        from pathlib import Path
        import base64
        from app.config import get_settings
        settings = get_settings()
        frame_dir = settings.ALERT_CLIPS_PATH / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_file = frame_dir / f"{event.camera_id}_{event.triggered_at.strftime('%Y%m%d%H%M%S%f')}.jpg"
        try:
            frame_file.write_bytes(base64.b64decode(event.frame_b64))
            frame_path = str(frame_file)
        except Exception:
            logger.warning("alert_frame_save_failed", camera_id=event.camera_id)

    alert = AlertEvent(
        camera_id=event.camera_id,
        alert_rule_id=rule.id if rule else None,
        triggered_at=event.triggered_at,
        detection_type=event.detection_type,
        zone_name=event.zone_name,
        confidence=event.confidence,
        severity=severity,
        rule_triggered=rule_name,
        bbox=event.bbox,
        track_id=event.track_id,
        frame_path=frame_path,
    )
    db.add(alert)
    await db.flush()

    logger.info(
        "alert_created",
        alert_id=alert.id,
        camera_id=event.camera_id,
        severity=severity.value,
        detection_type=event.detection_type,
    )

    # Queue Celery tasks
    try:
        from app.workers.alert_consumer import save_alert_clip, send_alert_notifications_task
        save_alert_clip.delay(alert.id)
        send_alert_notifications_task.delay(alert.id)
    except Exception:
        logger.exception("alert_task_queue_failed", alert_id=alert.id)

    # Publish to WebSocket via Redis
    try:
        from app.config import get_settings
        import redis as sync_redis
        settings = get_settings()
        r = sync_redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        payload = json.dumps({
            "type": "alert",
            "alert_id": alert.id,
            "severity": severity.value,
            "camera_id": event.camera_id,
            "detection_type": event.detection_type,
            "triggered_at": event.triggered_at.isoformat(),
        })
        r.publish("nvr:ws:broadcast", payload)
        r.close()
    except Exception:
        logger.warning("alert_ws_publish_failed", alert_id=alert.id)

    return alert


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: str,
    user: User,
    notes: str | None = None,
) -> AlertEventResponse:
    alert = await _load_alert(db, alert_id)
    alert.acknowledged = True
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    if notes is not None:
        alert.notes = notes
    audit_svc.log(db, "alert_acknowledged", user, "alert_event", alert_id,
                  detail={"notes": notes})
    return _alert_response(alert)


async def mark_false_positive(
    db: AsyncSession,
    alert_id: str,
    user: User,
    notes: str | None = None,
) -> AlertEventResponse:
    alert = await _load_alert(db, alert_id)
    alert.is_false_positive = True
    if notes is not None:
        alert.notes = notes
    audit_svc.log(db, "alert_false_positive", user, "alert_event", alert_id,
                  detail={"notes": notes})
    logger.info("alert_false_positive_marked", alert_id=alert_id, user_id=user.id)
    return _alert_response(alert)


async def set_legal_hold(
    db: AsyncSession,
    alert_id: str,
    hold: bool,
    user: User,
) -> AlertEventResponse:
    alert = await _load_alert(db, alert_id)
    alert.is_on_legal_hold = hold
    audit_svc.log(db, "alert_legal_hold_set", user, "alert_event", alert_id,
                  detail={"hold": hold})
    return _alert_response(alert)


async def get_alert_stats(
    db: AsyncSession,
    hours: int,
    user: User,
) -> AlertStatsResponse:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Severity counts
    sev_result = await db.execute(
        select(AlertEvent.severity, func.count().label("cnt"))
        .where(AlertEvent.triggered_at >= since)
        .group_by(AlertEvent.severity)
    )
    by_severity = {row.severity.value: row.cnt for row in sev_result}

    # Camera counts
    cam_result = await db.execute(
        select(AlertEvent.camera_id, func.count().label("cnt"))
        .where(AlertEvent.triggered_at >= since)
        .group_by(AlertEvent.camera_id)
    )
    by_camera = {row.camera_id: row.cnt for row in cam_result}

    # Rule counts (only events with a rule)
    rule_result = await db.execute(
        select(AlertEvent.alert_rule_id, func.count().label("cnt"))
        .where(
            AlertEvent.triggered_at >= since,
            AlertEvent.alert_rule_id.isnot(None),
        )
        .group_by(AlertEvent.alert_rule_id)
    )
    by_rule = {row.alert_rule_id: row.cnt for row in rule_result}

    # Hourly buckets — use literal_column to avoid asyncpg parameterizing 'hour'
    from sqlalchemy import literal_column
    hour_trunc = func.date_trunc(literal_column("'hour'"), AlertEvent.triggered_at)
    hour_result = await db.execute(
        select(hour_trunc.label("hour"), func.count().label("cnt"))
        .where(AlertEvent.triggered_at >= since)
        .group_by(hour_trunc)
        .order_by(hour_trunc)
    )
    by_hour = [{"hour": row.hour.isoformat(), "count": row.cnt} for row in hour_result]

    total_result = await db.execute(
        select(func.count()).where(AlertEvent.triggered_at >= since)
    )
    total = total_result.scalar_one()

    unack_result = await db.execute(
        select(func.count()).where(
            AlertEvent.triggered_at >= since,
            AlertEvent.acknowledged_at.is_(None),
        )
    )
    unacknowledged = unack_result.scalar_one()

    return AlertStatsResponse(
        total=total,
        unacknowledged=unacknowledged,
        by_severity=by_severity,
        by_camera=by_camera,
        by_rule=by_rule,
        by_hour=by_hour,
    )


async def list_alerts(
    db: AsyncSession,
    camera_id: str | None = None,
    severity: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    acknowledged: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AlertEventResponse], int]:
    stmt = select(AlertEvent)
    if camera_id:
        stmt = stmt.where(AlertEvent.camera_id == camera_id)
    if severity:
        stmt = stmt.where(AlertEvent.severity == severity)
    if from_dt:
        stmt = stmt.where(AlertEvent.triggered_at >= from_dt)
    if to_dt:
        stmt = stmt.where(AlertEvent.triggered_at <= to_dt)
    if acknowledged is not None:
        stmt = stmt.where(AlertEvent.acknowledged == acknowledged)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        stmt.order_by(AlertEvent.triggered_at.desc()).offset(offset).limit(page_size)
    )
    alerts = result.scalars().all()
    return [_alert_response(a) for a in alerts], total


async def get_alert(db: AsyncSession, alert_id: str) -> AlertEventResponse:
    return _alert_response(await _load_alert(db, alert_id))


async def _load_alert(db: AsyncSession, alert_id: str) -> AlertEvent:
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("AlertEvent", alert_id)
    return alert
