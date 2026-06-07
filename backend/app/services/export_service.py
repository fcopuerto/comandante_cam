"""
Export service — creates and retrieves export jobs.
Actual FFmpeg processing happens in workers/export.py (Celery).
"""
from datetime import datetime, timezone

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit_service as audit_svc
from app.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.camera import Camera
from app.models.export_job import ExportJob
from app.models.user import User
from app.schemas.recording import ExportCreate, ExportJobResponse

logger = structlog.get_logger(__name__)

_MAX_EXPORT_HOURS = 4


def _export_response(job: ExportJob, request: Request | None = None) -> ExportJobResponse:
    download_url = None
    if job.file_path and job.expires_at and job.expires_at > datetime.now(timezone.utc):
        if request:
            base = str(request.base_url).rstrip("/")
            download_url = f"{base}/api/v1/exports/{job.id}/download"

    return ExportJobResponse(
        id=job.id,
        camera_ids=list(job.camera_ids),
        from_dt=job.from_dt,
        to_dt=job.to_dt,
        status=job.status,
        progress_pct=job.progress_pct,
        file_size_bytes=job.file_size_bytes,
        checksum_sha256=job.checksum_sha256,
        password_protected=job.password_protected,
        watermark=job.watermark,
        watermark_text=job.watermark_text,
        error_message=job.error_message,
        requested_by=job.requested_by,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        download_url=download_url,
    )


async def create_export_job(
    db: AsyncSession,
    data: ExportCreate,
    user: User,
    request: Request | None = None,
) -> ExportJobResponse:
    # Validate time range
    if data.from_dt >= data.to_dt:
        raise ValidationError("from_dt", "from_dt must be before to_dt")

    duration_hours = (data.to_dt - data.from_dt).total_seconds() / 3600
    if duration_hours > _MAX_EXPORT_HOURS:
        raise ValidationError("to_dt", f"Export range cannot exceed {_MAX_EXPORT_HOURS} hours")

    # Validate cameras exist and are not deleted
    for cam_id in data.camera_ids:
        cam_result = await db.execute(
            select(Camera).where(Camera.id == cam_id, Camera.is_deleted.is_(False))
        )
        if not cam_result.scalar_one_or_none():
            raise NotFoundError("Camera", cam_id)

    # Find segments spanning the time range
    from app.services.recording_service import find_segments_in_range
    segments = await find_segments_in_range(db, list(data.camera_ids), data.from_dt, data.to_dt)
    if not segments:
        raise ValidationError("from_dt", "No recording segments found for the requested time range and cameras")

    # Estimate output size (sum segment sizes weighted by overlap ratio)
    estimated_bytes = 0
    for seg in segments:
        if seg.file_size_bytes and seg.duration_seconds and seg.duration_seconds > 0 and seg.ended_at:
            overlap_start = max(seg.started_at, data.from_dt)
            overlap_end = min(seg.ended_at, data.to_dt)
            overlap_s = (overlap_end - overlap_start).total_seconds()
            ratio = max(0.0, min(1.0, overlap_s / seg.duration_seconds))
            estimated_bytes += int(seg.file_size_bytes * ratio)

    if estimated_bytes > 4 * 1024 ** 3:
        logger.warning("export_large_estimate", estimated_gb=estimated_bytes / 1024 ** 3, user_id=user.id)

    job = ExportJob(
        camera_ids=list(data.camera_ids),
        from_dt=data.from_dt,
        to_dt=data.to_dt,
        watermark=data.watermark,
        watermark_text=data.watermark_text,
        password_protected=data.password_protected,
        requested_by=user.id,
    )
    db.add(job)
    await db.flush()

    # Queue Celery task
    try:
        from app.workers.export import export_clip
        export_clip.delay(job.id)
    except Exception:
        logger.exception("export_queue_failed", job_id=job.id)

    audit_svc.log(db, "export_requested", user, "export_job", job.id,
                  detail={"camera_ids": list(data.camera_ids), "from_dt": str(data.from_dt), "to_dt": str(data.to_dt)})

    resp = _export_response(job, request)
    resp.estimated_size_bytes = estimated_bytes
    return resp


async def get_export_status(
    db: AsyncSession,
    job_id: str,
    user: User,
    request: Request | None = None,
) -> ExportJobResponse:
    job = await _load_job(db, job_id)
    _check_access(job, user)
    return _export_response(job, request)


async def stream_export_file(
    db: AsyncSession,
    job_id: str,
    user: User,
    request: Request | None = None,
) -> StreamingResponse:
    from pathlib import Path
    from app.core.constants import ExportStatus

    job = await _load_job(db, job_id)
    _check_access(job, user)

    if job.status != ExportStatus.completed or not job.file_path:
        raise ValidationError("status", "Export is not ready for download")

    if job.expires_at and job.expires_at < datetime.now(timezone.utc):
        raise ValidationError("expires_at", "Export link has expired")

    file_path = Path(job.file_path).resolve()
    allowed_root = get_settings().EXPORT_PATH.resolve()
    if not str(file_path).startswith(str(allowed_root)):
        raise ForbiddenError("Export file is outside allowed storage path")
    if not file_path.exists():
        raise NotFoundError("Export file", job_id)

    file_size = file_path.stat().st_size
    suffix = file_path.suffix
    media_type = "application/zip" if suffix == ".zip" else "video/mp4"
    filename = f"nvr_export_{job.from_dt.strftime('%Y%m%d_%H%M%S')}{suffix}"

    audit_svc.log(db, "clip_exported", user, "export_job", job_id,
                  detail={"checksum": job.checksum_sha256, "file_size": file_size},
                  request=request)

    def _iter():
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
        },
    )


async def list_export_jobs(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ExportJobResponse], int]:
    from math import ceil
    from sqlalchemy import func
    from app.core.exceptions import ForbiddenError
    from app.models.role import Role

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    is_admin = role and "system:admin" in (role.permissions or [])

    stmt = select(ExportJob)
    if not is_admin:
        stmt = stmt.where(ExportJob.requested_by == user.id)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(stmt.order_by(ExportJob.created_at.desc()).offset(offset).limit(page_size))
    jobs = result.scalars().all()
    return [_export_response(j) for j in jobs], total


async def _load_job(db: AsyncSession, job_id: str) -> ExportJob:
    result = await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("ExportJob", job_id)
    return job


def _check_access(job: ExportJob, user: User) -> None:
    if job.requested_by != user.id:
        raise ForbiddenError("recordings:export")
