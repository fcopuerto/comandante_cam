"""Camera health check — runs every 60 seconds via Celery Beat."""
from datetime import datetime, timezone

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.core.constants import CameraStatus, RecordingMode
from app.models.camera import Camera

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


@celery_app.task(name="nvr.camera_health_check")
def camera_health_check() -> None:
    # Import here to avoid circular import at module load
    from app.workers.recording import RUNNING_PROCESSES, start_recording

    db = _get_session()
    try:
        cameras = db.execute(
            select(Camera).where(Camera.is_deleted.is_(False))
        ).scalars().all()

        for camera in cameras:
            proc = RUNNING_PROCESSES.get(camera.id)

            if camera.recording_mode == RecordingMode.off:
                # Should not be recording — stop if running
                if proc and proc.is_running():
                    proc.stop()
                    RUNNING_PROCESSES.pop(camera.id, None)
                continue

            if proc and proc.is_running():
                # Process alive — do a lightweight ONVIF ping to update last_seen
                _ping_camera(camera)
            else:
                # Not recording but should be — restart
                if proc:
                    RUNNING_PROCESSES.pop(camera.id, None)
                start_recording.delay(camera.id)
                logger.info("health_check_restart_triggered", camera_id=camera.id)

        db.commit()
    except Exception:
        logger.exception("health_check_error")
        db.rollback()
    finally:
        db.close()


def _ping_camera(camera: Camera) -> None:
    """Lightweight ONVIF ping — GetSystemDateAndTime. Updates last_seen on success."""
    db = _get_session()
    try:
        from onvif import ONVIFCamera
        from app.utils.encryption import get_encryption
        from app.utils.onvif_helpers import safe_get

        password = ""
        if camera.password_encrypted:
            try:
                password = get_encryption().decrypt(camera.password_encrypted)
            except Exception:
                pass

        try:
            from zeep.settings import Settings as ZeepSettings
            cam = ONVIFCamera(
                camera.ip_address, camera.onvif_port,
                camera.username or "", password,
                zeep_settings=ZeepSettings(strict=False),
            )
        except TypeError:
            cam = ONVIFCamera(camera.ip_address, camera.onvif_port, camera.username or "", password)

        device_svc = cam.create_devicemgmt_service()
        device_svc.GetSystemDateAndTime()

        db_camera = db.get(Camera, camera.id)
        if db_camera:
            db_camera.last_seen = datetime.now(timezone.utc)
            if db_camera.status not in (CameraStatus.recording,):
                db_camera.status = CameraStatus.online
        db.commit()

    except Exception as exc:
        err = str(exc).lower()
        db_camera = db.get(Camera, camera.id)
        if db_camera:
            if "401" in err or "auth" in err or "unauthorized" in err:
                db_camera.status = CameraStatus.unauthorized
            else:
                db_camera.status = CameraStatus.offline
            db_camera.last_error = str(exc)[:500]
        db.commit()
        logger.debug("camera_ping_failed", camera_id=camera.id, error=str(exc))
    finally:
        db.close()
