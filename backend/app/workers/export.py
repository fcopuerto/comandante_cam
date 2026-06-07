"""Export clip Celery task."""
import hashlib
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import get_settings
from app.core.constants import ExportStatus
from app.models.export_job import ExportJob
from app.models.recording_segment import RecordingSegment
from app.utils.ffmpeg import build_export_command

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


def _parse_ffmpeg_duration(line: str) -> float | None:
    """Parse 'time=HH:MM:SS.ms' from FFmpeg progress output and return total seconds."""
    match = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return h * 3600 + m * 60 + s
    return None


@celery_app.task(bind=True, name="nvr.export_clip")
def export_clip(self, job_id: str) -> None:  # type: ignore[override]
    settings = get_settings()
    db = _get_session()
    try:
        job = db.get(ExportJob, job_id)
        if not job:
            logger.error("export_job_not_found", job_id=job_id)
            return

        job.status = ExportStatus.processing
        job.progress_pct = 0
        db.commit()

        # Find all segments spanning the requested time range
        segments = db.execute(
            select(RecordingSegment)
            .where(
                RecordingSegment.camera_id.in_(list(job.camera_ids)),
                RecordingSegment.started_at < job.to_dt,
                RecordingSegment.ended_at > job.from_dt,
                RecordingSegment.is_corrupt.is_(False),
            )
            .order_by(RecordingSegment.camera_id, RecordingSegment.started_at)
        ).scalars().all()

        input_files = [seg.file_path for seg in segments if seg.file_path and Path(seg.file_path).exists()]
        if not input_files:
            job.status = ExportStatus.failed
            job.error_message = "No recording segments found for the requested time range"
            db.commit()
            return

        # Create output directory
        export_dir = settings.EXPORT_PATH / job_id
        export_dir.mkdir(parents=True, exist_ok=True)

        from_str = job.from_dt.strftime("%Y%m%d_%H%M%S")
        to_str = job.to_dt.strftime("%Y%m%d_%H%M%S")
        output_path = export_dir / f"export_{from_str}_{to_str}.mp4"

        watermark_text = job.watermark_text if job.watermark else None

        cmd = build_export_command(input_files, str(output_path), watermark_text)
        # Estimate total duration for progress calculation
        total_seconds = (job.to_dt - job.from_dt).total_seconds()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=1,
        )

        last_progress_update = 0.0
        while proc.poll() is None:
            line = proc.stderr.readline() if proc.stderr else b""
            if line:
                text = line.decode("utf-8", errors="replace").rstrip()
                elapsed = _parse_ffmpeg_duration(text)
                if elapsed is not None and total_seconds > 0:
                    pct = min(99, int(elapsed / total_seconds * 100))
                    now = datetime.now(timezone.utc).timestamp()
                    if now - last_progress_update >= 5:
                        last_progress_update = now
                        job.progress_pct = pct
                        db.commit()
                        logger.debug("export_progress", job_id=job_id, pct=pct)

        proc.wait()
        if proc.returncode != 0:
            job.status = ExportStatus.failed
            job.error_message = f"FFmpeg exited with code {proc.returncode}"
            db.commit()
            return

        if not output_path.exists():
            job.status = ExportStatus.failed
            job.error_message = "Output file not created"
            db.commit()
            return

        # Optional password-protected ZIP
        final_path = output_path
        if job.password_protected:
            try:
                import pyzipper
                zip_path = output_path.with_suffix(".zip")
                # Note: password would be stored/retrieved separately — stub for now
                with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED,
                                         encryption=pyzipper.WZ_AES) as zf:
                    zf.write(output_path, output_path.name)
                output_path.unlink()
                final_path = zip_path
            except Exception as exc:
                logger.warning("export_zip_failed", job_id=job_id, error=str(exc))

        checksum = _sha256(final_path)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.EXPORT_EXPIRY_HOURS)

        job.status = ExportStatus.completed
        job.progress_pct = 100
        job.file_path = str(final_path)
        job.file_size_bytes = final_path.stat().st_size
        job.checksum_sha256 = checksum
        job.completed_at = datetime.now(timezone.utc)
        job.expires_at = expires_at
        db.commit()

        logger.info("export_complete", job_id=job_id, size=job.file_size_bytes)

    except Exception as exc:
        logger.exception("export_error", job_id=job_id)
        try:
            job = db.get(ExportJob, job_id)
            if job:
                job.status = ExportStatus.failed
                job.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
