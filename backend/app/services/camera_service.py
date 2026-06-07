import re
from datetime import datetime, timedelta, timezone
from typing import Any

_MAC_RE = re.compile(r'^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$')


def _valid_mac(value: str | None) -> str | None:
    return value if value and _MAC_RE.match(value) else None

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.onvif_service as onvif_svc
from app.core.exceptions import CameraConnectionError, NotFoundError
from app.models.alert_event import AlertEvent
from app.models.camera import Camera
from app.models.recording_segment import RecordingSegment
from app.schemas.camera import CameraCreate, CameraStats, CameraUpdate
from app.utils.encryption import get_encryption

logger = structlog.get_logger(__name__)


async def _load_camera(db: AsyncSession, camera_id: str) -> Camera:
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.is_deleted.is_(False))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera", camera_id)
    return camera


async def register_camera(
    db: AsyncSession, data: CameraCreate, created_by_id: str
) -> Camera:
    # Probe first — fail fast if unreachable
    probe = await onvif_svc.probe_camera(
        ip=data.ip_address,
        port=data.onvif_port,
        username=data.username or "",
        password=data.password or "",
    )

    password_encrypted: bytes | None = None
    if data.password:
        password_encrypted = get_encryption().encrypt(data.password)

    camera = Camera(
        name=data.name,
        description=data.description,
        ip_address=data.ip_address,
        onvif_port=data.onvif_port,
        username=data.username,
        password_encrypted=password_encrypted,
        onvif_profile_main=probe.onvif_profile_main,
        onvif_profile_sub=probe.onvif_profile_sub,
        manufacturer=probe.manufacturer,
        model=probe.model,
        firmware_version=probe.firmware_version,
        serial_number=probe.serial_number,
        mac_address=_valid_mac(probe.mac_address),
        rtsp_main_url=probe.rtsp_main_url,
        rtsp_sub_url=probe.rtsp_sub_url,
        resolution_main=probe.resolution_main,
        resolution_sub=probe.resolution_sub,
        fps=probe.fps or 25,
        bitrate_kbps=probe.bitrate_kbps or 2000,
        ptz_enabled=probe.ptz_enabled,
        group_id=data.group_id,
        zone_location=data.zone_location,
        building=data.building,
        floor=data.floor,
        map_x=data.map_x,
        map_y=data.map_y,
        is_vpn=data.is_vpn,
        vpn_host=data.vpn_host,
        tags=data.tags,
        notes=data.notes,
        recording_mode=data.recording_mode,
        retention_days=data.retention_days,
        created_by=created_by_id,
    )
    db.add(camera)
    await db.flush()
    logger.info("camera_added", camera_id=camera.id, ip=camera.ip_address)
    return camera


async def update_camera(
    db: AsyncSession, camera_id: str, data: CameraUpdate, user_id: str
) -> Camera:
    camera = await _load_camera(db, camera_id)

    ip_changed = data.ip_address is not None and data.ip_address != camera.ip_address

    if ip_changed:
        new_ip = data.ip_address or camera.ip_address
        new_port = data.onvif_port or camera.onvif_port
        new_user = data.username if data.username else (camera.username or "")
        new_pass = ""
        if camera.password_encrypted:
            new_pass = get_encryption().decrypt(camera.password_encrypted)
        if data.password:
            new_pass = data.password
        probe = await onvif_svc.probe_camera(new_ip, new_port, new_user, new_pass)
        camera.onvif_profile_main = probe.onvif_profile_main or camera.onvif_profile_main
        camera.onvif_profile_sub = probe.onvif_profile_sub or camera.onvif_profile_sub
        camera.manufacturer = probe.manufacturer or camera.manufacturer
        camera.model = probe.model or camera.model
        camera.firmware_version = probe.firmware_version or camera.firmware_version
        camera.serial_number = probe.serial_number or camera.serial_number
        camera.rtsp_main_url = probe.rtsp_main_url or camera.rtsp_main_url
        camera.rtsp_sub_url = probe.rtsp_sub_url or camera.rtsp_sub_url
        camera.resolution_main = probe.resolution_main or camera.resolution_main
        camera.resolution_sub = probe.resolution_sub or camera.resolution_sub

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "password":
            if value:
                camera.password_encrypted = get_encryption().encrypt(value)
        elif field == "username":
            if value:
                camera.username = value
        else:
            setattr(camera, field, value)

    logger.info("camera_configured", camera_id=camera.id, updated_by=user_id)
    return camera


async def delete_camera(db: AsyncSession, camera_id: str) -> None:
    camera = await _load_camera(db, camera_id)
    camera.is_deleted = True
    camera.deleted_at = datetime.now(timezone.utc)
    logger.info("camera_removed", camera_id=camera_id)


async def get_camera(db: AsyncSession, camera_id: str) -> Camera:
    return await _load_camera(db, camera_id)


async def get_cameras(
    db: AsyncSession,
    group_id: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Camera], int]:
    from sqlalchemy import or_

    stmt = select(Camera).where(Camera.is_deleted.is_(False))

    if group_id is not None:
        stmt = stmt.where(Camera.group_id == group_id)
    if status is not None:
        stmt = stmt.where(Camera.status == status)
    if tags:
        from sqlalchemy.dialects.postgresql import ARRAY
        from sqlalchemy import String, cast
        for tag in tags:
            stmt = stmt.where(Camera.tags.contains(cast([tag], ARRAY(String))))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Camera.name.ilike(pattern), Camera.zone_location.ilike(pattern))
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Camera.name).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    cameras = list(result.scalars().all())

    return cameras, total


async def get_camera_stats(db: AsyncSession, camera_id: str) -> CameraStats:
    await _load_camera(db, camera_id)  # ensures it exists
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    seg_stmt = select(
        func.coalesce(func.sum(RecordingSegment.duration_seconds), 0).label("total_seconds"),
        func.coalesce(func.sum(RecordingSegment.file_size_bytes), 0).label("total_bytes"),
    ).where(
        RecordingSegment.camera_id == camera_id,
        RecordingSegment.started_at >= cutoff,
    )
    seg_result = await db.execute(seg_stmt)
    seg_row = seg_result.one()

    alert_stmt = select(func.count()).where(
        AlertEvent.camera_id == camera_id,
        AlertEvent.triggered_at >= cutoff,
    )
    alert_result = await db.execute(alert_stmt)
    alert_count = alert_result.scalar_one()

    return CameraStats(
        camera_id=camera_id,
        recording_hours_30d=round(seg_row.total_seconds / 3600, 2),
        storage_used_bytes=seg_row.total_bytes,
        alert_count_30d=alert_count,
    )
