"""Purge old recording segments and expired exports — runs daily at 03:00 UTC."""
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.models.camera import Camera
from app.models.export_job import ExportJob
from app.models.recording_segment import RecordingSegment
from app.models.system_event import SystemEvent

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


def _storage_usage_pct() -> float:
    settings = get_settings()
    try:
        stat = shutil.disk_usage(str(settings.STORAGE_PATH))
        return stat.used / stat.total * 100
    except (OSError, ZeroDivisionError):
        return 0.0


def _delete_segment(db, segment: RecordingSegment) -> None:
    try:
        if segment.file_path:
            p = Path(segment.file_path)
            if p.exists():
                p.unlink()
    except OSError as exc:
        logger.warning("segment_file_delete_failed", path=segment.file_path, error=str(exc))
    try:
        if segment.thumbnail_path:
            t = Path(segment.thumbnail_path)
            if t.exists():
                t.unlink()
    except OSError:
        pass
    db.delete(segment)


@celery_app.task(name="nvr.purge_old_segments")
def purge_old_segments() -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    deleted_segments = 0
    deleted_bytes = 0

    db = _get_session()
    try:
        # Purge expired recording segments (per-camera retention_days)
        cameras = db.execute(select(Camera).where(Camera.is_deleted.is_(False))).scalars().all()
        for camera in cameras:
            cutoff = now - timedelta(days=camera.retention_days)
            batch = db.execute(
                select(RecordingSegment)
                .where(
                    RecordingSegment.camera_id == camera.id,
                    RecordingSegment.ended_at < cutoff,
                    RecordingSegment.is_on_legal_hold.is_(False),
                )
                .limit(100)
            ).scalars().all()

            for seg in batch:
                deleted_bytes += seg.file_size_bytes or 0
                _delete_segment(db, seg)
                deleted_segments += 1

        # Purge expired exports
        expired_exports = db.execute(
            select(ExportJob).where(
                ExportJob.expires_at < now,
                ExportJob.expires_at.isnot(None),
            )
        ).scalars().all()
        for job in expired_exports:
            try:
                if job.file_path:
                    p = Path(job.file_path)
                    if p.exists():
                        p.unlink()
                    # Remove the parent dir if empty
                    if p.parent.exists() and not any(p.parent.iterdir()):
                        p.parent.rmdir()
            except OSError:
                pass
            db.delete(job)

        # Audit log retention
        AUDIT_LOG_RETENTION_DAYS = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "365"))
        IP_RETENTION_DAYS = int(os.environ.get("IP_RETENTION_DAYS", "90"))

        audit_cutoff = now - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
        ip_cutoff = now - timedelta(days=IP_RETENTION_DAYS)

        from app.models.audit_log import AuditLog
        from sqlalchemy import delete, update

        db.execute(delete(AuditLog).where(AuditLog.created_at < audit_cutoff))

        db.execute(
            update(AuditLog)
            .where(AuditLog.created_at < ip_cutoff, AuditLog.ip_address.isnot(None))
            .values(ip_address=None)
        )

        db.commit()
        logger.info("purge_complete", segments=deleted_segments, freed_bytes=deleted_bytes)

        # Record storage stats
        usage_pct = _storage_usage_pct()
        evt = SystemEvent(
            event_type="storage_stats",
            severity="info",
            message=f"Storage at {usage_pct:.1f}% after purge",
            detail={"usage_pct": usage_pct, "deleted_segments": deleted_segments},
        )
        db.add(evt)
        db.commit()

        # Escalate if over thresholds
        if usage_pct >= settings.STORAGE_CRITICAL_PCT:
            logger.warning("storage_critical", usage_pct=usage_pct)
            alert_evt = SystemEvent(
                event_type="storage_critical",
                severity="critical",
                message=f"Storage critical at {usage_pct:.1f}%",
                detail={"usage_pct": usage_pct},
            )
            db.add(alert_evt)
            db.commit()
            emergency_purge(db)
        elif usage_pct >= settings.STORAGE_WARNING_PCT:
            warn_evt = SystemEvent(
                event_type="storage_warning",
                severity="warning",
                message=f"Storage warning at {usage_pct:.1f}%",
                detail={"usage_pct": usage_pct},
            )
            db.add(warn_evt)
            db.commit()

    except Exception:
        logger.exception("purge_error")
        db.rollback()
    finally:
        db.close()


def emergency_purge(db) -> None:
    """Delete oldest segments (ignoring retention, never legal holds) until below 85%."""
    logger.warning("emergency_purge_started")
    deleted = 0
    while _storage_usage_pct() > 85.0:
        batch = db.execute(
            select(RecordingSegment)
            .where(RecordingSegment.is_on_legal_hold.is_(False))
            .order_by(RecordingSegment.started_at)
            .limit(50)
        ).scalars().all()
        if not batch:
            break
        for seg in batch:
            _delete_segment(db, seg)
            deleted += 1
        try:
            db.commit()
        except Exception:
            db.rollback()
            break
    logger.warning("emergency_purge_complete", deleted=deleted)
