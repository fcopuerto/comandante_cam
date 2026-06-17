"""
Recording Celery tasks.
RUNNING_PROCESSES is module-level (in-worker state) — do not access from FastAPI.
"""
import hashlib
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.core.constants import CameraStatus, RecordingMode, SegmentType
from app.models.camera import Camera
from app.models.recording_segment import RecordingSegment
from app.models.system_event import SystemEvent
from app.utils.ffmpeg import (
    FFmpegEventType,
    FFmpegProcess,
    build_continuous_command,
    build_thumbnail_command,
)

logger = structlog.get_logger(__name__)

# In-worker process registry — keyed by camera_id
RUNNING_PROCESSES: dict[str, FFmpegProcess] = {}

_sync_engine = None
_SyncSession = None


def _get_sync_session() -> sessionmaker:
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        settings = get_settings()
        _sync_engine = create_engine(
            settings.DATABASE_URL_SYNC,
            pool_size=5,
            pool_pre_ping=True,
        )
        _SyncSession = sessionmaker(bind=_sync_engine, expire_on_commit=False)
    return _SyncSession


@contextmanager
def _db() -> Generator[Session, None, None]:
    SessionLocal = _get_sync_session()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _generate_thumbnail(video_path: Path) -> Path | None:
    thumb_path = video_path.with_suffix(".jpg")
    cmd = build_thumbnail_command(str(video_path), str(thumb_path))
    try:
        subprocess.run(cmd, timeout=15, capture_output=True)
        if thumb_path.exists():
            return thumb_path
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _close_segment(
    camera_id: str,
    file_path: Path,
    started_at: datetime,
    segment_type: SegmentType = SegmentType.continuous,
) -> None:
    """Write a completed RecordingSegment row to the DB."""
    if not file_path.exists():
        return
    ended_at = datetime.now(timezone.utc)
    duration = int((ended_at - started_at).total_seconds())
    size = file_path.stat().st_size
    checksum = _sha256(file_path)
    thumb = _generate_thumbnail(file_path)

    with _db() as db:
        seg = RecordingSegment(
            camera_id=camera_id,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=size,
            segment_type=segment_type,
            checksum_sha256=checksum,
            thumbnail_path=str(thumb) if thumb else None,
        )
        db.add(seg)
    logger.info(
        "segment_closed",
        camera_id=camera_id,
        file=file_path.name,
        duration_s=duration,
        size_bytes=size,
    )


@celery_app.task(bind=True, max_retries=20, name="nvr.start_recording")
def start_recording(self, camera_id: str) -> None:  # type: ignore[override]
    # Idempotency — already recording
    proc = RUNNING_PROCESSES.get(camera_id)
    if proc and proc.is_running():
        logger.debug("recording_already_running", camera_id=camera_id)
        return

    settings = get_settings()

    with _db() as db:
        camera = db.get(Camera, camera_id)
        if not camera or camera.is_deleted:
            logger.warning("recording_camera_not_found", camera_id=camera_id)
            return
        if camera.recording_mode == RecordingMode.off:
            return

        rtsp_url = camera.rtsp_main_url
        if not rtsp_url and camera.password_encrypted:
            from app.utils.encryption import get_encryption
            # Try to refresh the URL via ONVIF (best effort)
            logger.warning("recording_no_rtsp_url", camera_id=camera_id)
        if not rtsp_url:
            logger.warning("recording_no_rtsp_url", camera_id=camera_id)
            return

        mode = camera.recording_mode

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = settings.STORAGE_PATH / camera_id / today
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_continuous_command(
        rtsp_url,
        str(output_dir),
        camera_id,
        osd_camera_name=camera.name if camera.osd_enabled and camera.osd_label else None,
        osd_clock=camera.osd_enabled and camera.osd_clock,
    )
    proc = FFmpegProcess(camera_id, cmd)
    try:
        proc.start()
    except Exception as exc:
        logger.error("ffmpeg_start_failed", camera_id=camera_id, error=str(exc))
        retry_in = min(30 * (self.request.retries + 1), 600)
        raise self.retry(exc=exc, countdown=retry_in)

    RUNNING_PROCESSES[camera_id] = proc

    with _db() as db:
        camera = db.get(Camera, camera_id)
        if camera:
            camera.status = CameraStatus.recording
            camera.consecutive_errors = 0

    # Monitoring loop
    current_segment_path: Path | None = None
    current_segment_start = datetime.now(timezone.utc)
    consecutive_errors = 0
    MAX_ERRORS = 10

    while proc.is_running():
        line = proc.read_stderr_line()
        if line:
            logger.debug("ffmpeg_stderr", camera_id=camera_id, line=line)
            event = proc.parse_stderr(line)
            if event:
                if event.type == FFmpegEventType.segment_created:
                    # A new segment file was opened — close the previous one
                    if current_segment_path and current_segment_path.exists():
                        _close_segment(camera_id, current_segment_path, current_segment_start)
                    # Parse new filename from the FFmpeg log line
                    # "Opening '...' for writing"
                    import re
                    match = re.search(r"Opening '([^']+\.mp4)' for writing", line)
                    if match:
                        current_segment_path = Path(match.group(1))
                        current_segment_start = datetime.now(timezone.utc)

                elif event.type in (FFmpegEventType.stream_error, FFmpegEventType.connection_refused, FFmpegEventType.corrupt_stream):
                    consecutive_errors += 1
                    logger.warning(
                        "ffmpeg_stream_error",
                        camera_id=camera_id,
                        event=event.type,
                        count=consecutive_errors,
                    )
                    with _db() as db:
                        camera = db.get(Camera, camera_id)
                        if camera:
                            camera.consecutive_errors = consecutive_errors
                            camera.last_error = event.message[:500]

                    if consecutive_errors >= MAX_ERRORS:
                        logger.error("recording_max_errors", camera_id=camera_id)
                        with _db() as db:
                            camera = db.get(Camera, camera_id)
                            if camera:
                                camera.status = CameraStatus.error
                            evt = SystemEvent(
                                event_type="stream_error",
                                severity="critical",
                                message=f"Camera {camera_id} reached {MAX_ERRORS} consecutive errors",
                                detail={"camera_id": camera_id},
                            )
                            db.add(evt)
                        proc.stop()
                        RUNNING_PROCESSES.pop(camera_id, None)
                        return

                elif event.type == FFmpegEventType.reconnecting:
                    logger.info("ffmpeg_reconnecting", camera_id=camera_id)

                elif event.type == FFmpegEventType.clean_exit:
                    break
        else:
            # Rotate output directory at midnight
            new_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if new_today != today:
                today = new_today
                output_dir = settings.STORAGE_PATH / camera_id / today
                output_dir.mkdir(parents=True, exist_ok=True)

            time.sleep(0.1)

    # Process exited
    RUNNING_PROCESSES.pop(camera_id, None)
    return_code = proc._proc.returncode if proc._proc else -1

    # Close final segment
    if current_segment_path and current_segment_path.exists():
        _close_segment(camera_id, current_segment_path, current_segment_start)

    with _db() as db:
        camera = db.get(Camera, camera_id)
        if camera and camera.status == CameraStatus.recording:
            camera.status = CameraStatus.offline

    # Restart unless it was a clean shutdown (return code 0 or 255 from SIGTERM)
    if return_code not in (0, 255, -15):
        logger.warning("ffmpeg_unexpected_exit", camera_id=camera_id, code=return_code)
        retry_in = min(30 * (self.request.retries + 1), 600)
        raise self.retry(countdown=retry_in)


@celery_app.task(name="nvr.stop_recording")
def stop_recording(camera_id: str) -> None:
    proc = RUNNING_PROCESSES.pop(camera_id, None)
    if proc:
        proc.stop()
        logger.info("recording_stopped", camera_id=camera_id)
    with _db() as db:
        camera = db.get(Camera, camera_id)
        if camera and camera.status == CameraStatus.recording:
            camera.status = CameraStatus.offline


@celery_app.task(name="nvr.start_all_recordings")
def start_all_recordings() -> None:
    """Called on worker startup to resume recording for all active cameras."""
    with _db() as db:
        result = db.execute(
            select(Camera).where(
                Camera.recording_mode != RecordingMode.off,
                Camera.is_deleted.is_(False),
            )
        )
        cameras = result.scalars().all()

    for camera in cameras:
        start_recording.delay(camera.id)
    logger.info("start_all_recordings_queued", count=len(cameras))
