from datetime import datetime, timezone
from math import ceil

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.camera_service as camera_svc
import app.services.onvif_service as onvif_svc
from app.core.exceptions import CameraConnectionError, NotFoundError
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.camera import Camera
from app.models.camera_permission import CameraPermission
from app.models.detection_zone import DetectionZone
from app.models.recording_schedule import RecordingSchedule
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.camera import (
    CameraCreate,
    CameraPermissionResponse,
    CameraPermissionSet,
    CameraProbeResult,
    CameraResponse,
    CameraStats,
    CameraTestResult,
    CameraUpdate,
    DiscoverRequest,
    DiscoveredCamera,
    Page,
    ProbeRequest,
    PTZMoveRequest,
    PTZPreset,
    PTZPresetCreate,
    RecordingModeUpdate,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
    StreamUrlResponse,
    ZoneBulkUpdateRequest,
    ZoneCreate,
    ZoneResponse,
    ZoneUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/cameras", tags=["cameras"])


def _camera_response(camera: Camera) -> CameraResponse:
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        description=camera.description,
        ip_address=camera.ip_address,
        onvif_port=camera.onvif_port,
        username=camera.username,
        onvif_profile_main=camera.onvif_profile_main,
        onvif_profile_sub=camera.onvif_profile_sub,
        manufacturer=camera.manufacturer,
        model=camera.model,
        firmware_version=camera.firmware_version,
        serial_number=camera.serial_number,
        mac_address=str(camera.mac_address) if camera.mac_address else None,
        is_vpn=camera.is_vpn,
        vpn_host=camera.vpn_host,
        group_id=camera.group_id,
        zone_location=camera.zone_location,
        building=camera.building,
        floor=camera.floor,
        map_x=camera.map_x,
        map_y=camera.map_y,
        status=camera.status,
        recording_mode=camera.recording_mode,
        resolution_main=camera.resolution_main,
        resolution_sub=camera.resolution_sub,
        fps=camera.fps,
        bitrate_kbps=camera.bitrate_kbps,
        codec=camera.codec,
        retention_days=camera.retention_days,
        pre_event_seconds=camera.pre_event_seconds,
        post_event_seconds=camera.post_event_seconds,
        ptz_enabled=camera.ptz_enabled,
        tags=list(camera.tags or []),
        notes=camera.notes,
        detection_enabled=camera.detection_enabled,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        created_by=camera.created_by,
    )


# ── Camera CRUD ───────────────────────────────────────────────────────────────

@router.get("", response_model=Page[CameraResponse])
async def list_cameras(
    group_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[CameraResponse]:
    cameras, total = await camera_svc.get_cameras(
        db, group_id=group_id, status=status, tags=tags,
        search=search, page=page, page_size=page_size,
    )
    return Page(
        items=[_camera_response(c) for c in cameras],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraResponse:
    try:
        camera = await camera_svc.register_camera(db, body, created_by_id=user.id)
    except CameraConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Camera unreachable: {exc.reason}",
        ) from exc
    return _camera_response(camera)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraResponse:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _camera_response(camera)


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraResponse:
    try:
        camera = await camera_svc.update_camera(db, camera_id, body, user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CameraConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Camera unreachable: {exc.reason}",
        ) from exc
    return _camera_response(camera)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        await camera_svc.delete_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── Discovery ─────────────────────────────────────────────────────────────────

@router.post("/discover", response_model=list[DiscoveredCamera])
async def discover_cameras(
    body: DiscoverRequest,
    user: User = Depends(get_current_user),
) -> list[DiscoveredCamera]:
    return await onvif_svc.discover_cameras(body.subnet, timeout=body.timeout)


@router.post("/discover/onvif", response_model=CameraProbeResult)
async def probe_camera(
    body: ProbeRequest,
    user: User = Depends(get_current_user),
) -> CameraProbeResult:
    try:
        return await onvif_svc.probe_camera(body.ip, body.port, body.username, body.password)
    except CameraConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Camera unreachable: {exc.reason}",
        ) from exc


class TestConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ip_address: str
    port: int = 80
    username: str = ""
    password: str = ""


class TestConnectionResponse(BaseModel):
    onvif: bool
    rtsp: bool
    error: str | None = None


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection_new(
    body: TestConnectionRequest,
    _user: User = Depends(get_current_user),
) -> TestConnectionResponse:
    try:
        result = await onvif_svc.probe_camera(
            body.ip_address, body.port, body.username, body.password
        )
        return TestConnectionResponse(onvif=True, rtsp=result.rtsp_reachable)
    except Exception as exc:
        return TestConnectionResponse(onvif=False, rtsp=False, error=str(exc))


# ── Per-camera actions ────────────────────────────────────────────────────────

@router.post("/{camera_id}/test-connection", response_model=CameraTestResult)
async def test_connection(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraTestResult:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    from app.utils.encryption import get_encryption
    password = ""
    if camera.password_encrypted:
        password = get_encryption().decrypt(camera.password_encrypted)

    try:
        probe = await onvif_svc.probe_camera(
            camera.ip_address, camera.onvif_port, camera.username or "", password
        )
        return CameraTestResult(
            onvif_reachable=True,
            rtsp_reachable=probe.rtsp_reachable,
            probe_result=probe,
        )
    except CameraConnectionError as exc:
        return CameraTestResult(
            onvif_reachable=False,
            rtsp_reachable=False,
            error=exc.reason,
        )


@router.post("/{camera_id}/sync-time", status_code=status.HTTP_204_NO_CONTENT)
async def sync_time(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    success = await onvif_svc.sync_time(camera)
    if success:
        camera.ntp_synced = True
        camera.last_ntp_sync = datetime.now(timezone.utc)
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Time sync failed — check camera connectivity",
        )


@router.get("/{camera_id}/capabilities", response_model=CameraProbeResult)
async def get_capabilities(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraProbeResult:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    from app.utils.encryption import get_encryption
    from app.core.constants import Codec
    password = ""
    if camera.password_encrypted:
        password = get_encryption().decrypt(camera.password_encrypted)

    try:
        return await onvif_svc.probe_camera(
            camera.ip_address, camera.onvif_port, camera.username or "", password
        )
    except CameraConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Camera unreachable: {exc.reason}",
        ) from exc


@router.get("/{camera_id}/snapshot")
async def get_snapshot(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        jpeg = await onvif_svc.get_snapshot(camera)
    except CameraConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Snapshot failed: {exc.reason}",
        ) from exc
    return Response(content=jpeg, media_type="image/jpeg")


@router.patch("/{camera_id}/recording-mode", response_model=CameraResponse)
async def update_recording_mode(
    camera_id: str,
    body: RecordingModeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraResponse:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    camera.recording_mode = body.mode
    logger.info("recording_mode_changed", camera_id=camera_id, mode=body.mode)
    return _camera_response(camera)


@router.get("/{camera_id}/stream-url", response_model=StreamUrlResponse)
async def get_stream_url(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamUrlResponse:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # HLS stream management is handled in Session 7; return the URL format
    return StreamUrlResponse(
        hls_url=f"/hls/{camera_id}/index.m3u8",
        sub_hls_url=f"/hls/{camera_id}/sub/index.m3u8",
        camera=_camera_response(camera),
    )


@router.get("/{camera_id}/stats", response_model=CameraStats)
async def get_stats(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CameraStats:
    try:
        return await camera_svc.get_camera_stats(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── PTZ ───────────────────────────────────────────────────────────────────────

@router.get("/{camera_id}/ptz/presets", response_model=list[PTZPreset])
async def list_ptz_presets(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PTZPreset]:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not camera.ptz_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PTZ not enabled for this camera")
    return await onvif_svc.get_ptz_presets(camera)


@router.post("/{camera_id}/ptz/presets", response_model=PTZPreset, status_code=status.HTTP_201_CREATED)
async def save_ptz_preset(
    camera_id: str,
    body: PTZPresetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PTZPreset:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not camera.ptz_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PTZ not enabled for this camera")
    try:
        token = await onvif_svc.save_preset(camera, body.name)
    except CameraConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.reason) from exc
    return PTZPreset(token=token, name=body.name)


@router.post("/{camera_id}/ptz/presets/{preset_token}/goto", status_code=status.HTTP_204_NO_CONTENT)
async def goto_ptz_preset(
    camera_id: str,
    preset_token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not camera.ptz_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PTZ not enabled for this camera")
    await onvif_svc.goto_preset(camera, preset_token)


@router.delete("/{camera_id}/ptz/presets/{preset_token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ptz_preset(
    camera_id: str,
    preset_token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not camera.ptz_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PTZ not enabled for this camera")
    # PTZ preset deletion runs in executor
    loop = __import__("asyncio").get_event_loop()
    def _delete():
        from onvif import ONVIFCamera
        from app.utils.encryption import get_encryption
        password = get_encryption().decrypt(camera.password_encrypted) if camera.password_encrypted else ""
        try:
            from zeep.settings import Settings as ZeepSettings
            cam = ONVIFCamera(camera.ip_address, camera.onvif_port, camera.username or "", password, zeep_settings=ZeepSettings(strict=False))
        except TypeError:
            cam = ONVIFCamera(camera.ip_address, camera.onvif_port, camera.username or "", password)
        ptz_svc = cam.create_ptz_service()
        ptz_svc.RemovePreset({"ProfileToken": camera.onvif_profile_main or "", "PresetToken": preset_token})
    try:
        await loop.run_in_executor(None, _delete)
    except Exception:
        pass  # Best effort; camera may already have removed the preset


@router.post("/{camera_id}/ptz/move", status_code=status.HTTP_204_NO_CONTENT)
async def ptz_move(
    camera_id: str,
    body: PTZMoveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not camera.ptz_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PTZ not enabled for this camera")
    await onvif_svc.continuous_move(camera, body.pan, body.tilt, body.zoom)


@router.post("/{camera_id}/ptz/stop", status_code=status.HTTP_204_NO_CONTENT)
async def ptz_stop(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        camera = await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await onvif_svc.stop_ptz(camera)


# ── Schedules ─────────────────────────────────────────────────────────────────

def _schedule_response(sched: RecordingSchedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=sched.id,
        camera_id=sched.camera_id,
        name=sched.name,
        days_of_week=list(sched.days_of_week or []),
        time_start=sched.time_start.strftime("%H:%M"),
        time_end=sched.time_end.strftime("%H:%M"),
        recording_mode=sched.recording_mode,
        enabled=sched.enabled,
        created_at=sched.created_at,
    )


@router.get("/{camera_id}/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduleResponse]:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await db.execute(
        select(RecordingSchedule).where(RecordingSchedule.camera_id == camera_id)
    )
    return [_schedule_response(s) for s in result.scalars().all()]


@router.post("/{camera_id}/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    camera_id: str,
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleResponse:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    from datetime import time as dt_time
    h_start, m_start = map(int, body.time_start.split(":"))
    h_end, m_end = map(int, body.time_end.split(":"))

    sched = RecordingSchedule(
        camera_id=camera_id,
        name=body.name,
        days_of_week=body.days_of_week,
        time_start=dt_time(h_start, m_start),
        time_end=dt_time(h_end, m_end),
        recording_mode=body.recording_mode,
        enabled=body.enabled,
    )
    db.add(sched)
    await db.flush()
    return _schedule_response(sched)


@router.patch("/{camera_id}/schedules/{sched_id}", response_model=ScheduleResponse)
async def update_schedule(
    camera_id: str,
    sched_id: str,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleResponse:
    result = await db.execute(
        select(RecordingSchedule).where(
            RecordingSchedule.id == sched_id, RecordingSchedule.camera_id == camera_id
        )
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    from datetime import time as dt_time
    if body.name is not None:
        sched.name = body.name
    if body.days_of_week is not None:
        sched.days_of_week = body.days_of_week
    if body.time_start is not None:
        h, m = map(int, body.time_start.split(":"))
        sched.time_start = dt_time(h, m)
    if body.time_end is not None:
        h, m = map(int, body.time_end.split(":"))
        sched.time_end = dt_time(h, m)
    if body.recording_mode is not None:
        sched.recording_mode = body.recording_mode
    if body.enabled is not None:
        sched.enabled = body.enabled
    return _schedule_response(sched)


@router.delete("/{camera_id}/schedules/{sched_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    camera_id: str,
    sched_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(RecordingSchedule).where(
            RecordingSchedule.id == sched_id, RecordingSchedule.camera_id == camera_id
        )
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    await db.delete(sched)


# ── Detection zones ───────────────────────────────────────────────────────────

def _zone_response(zone: DetectionZone) -> ZoneResponse:
    return ZoneResponse(
        id=zone.id,
        camera_id=zone.camera_id,
        name=zone.name,
        polygon=zone.polygon,
        restricted=zone.restricted,
        enabled=zone.enabled,
        working_hours_start=zone.working_hours_start.strftime("%H:%M") if zone.working_hours_start else None,
        working_hours_end=zone.working_hours_end.strftime("%H:%M") if zone.working_hours_end else None,
        timezone=zone.timezone,
        dwell_threshold_s=zone.dwell_threshold_s,
        color=zone.color,
        created_at=zone.created_at,
        updated_at=zone.updated_at,
    )


@router.get("/{camera_id}/zones", response_model=list[ZoneResponse])
async def list_zones(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ZoneResponse]:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await db.execute(
        select(DetectionZone).where(DetectionZone.camera_id == camera_id)
    )
    return [_zone_response(z) for z in result.scalars().all()]


@router.put("/{camera_id}/zones", response_model=list[ZoneResponse])
async def replace_zones(
    camera_id: str,
    body: ZoneBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    redis=Depends(get_redis),
) -> list[ZoneResponse]:
    """Replace all zones for a camera and publish updated config to Redis."""
    import json
    from datetime import time as dt_time

    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Delete existing zones
    existing = await db.execute(
        select(DetectionZone).where(DetectionZone.camera_id == camera_id)
    )
    for z in existing.scalars().all():
        await db.delete(z)

    def _parse_time(s: str | None):
        if not s:
            return None
        h, m = map(int, s.split(":"))
        return dt_time(h, m)

    # Create new zones
    new_zones = []
    redis_payload = []
    for item in body.zones:
        zone = DetectionZone(
            camera_id=camera_id,
            name=item.name,
            polygon=item.polygon,
            restricted=item.restricted,
            enabled=item.enabled,
            working_hours_start=_parse_time(item.working_hours_start),
            working_hours_end=_parse_time(item.working_hours_end),
            timezone=item.timezone,
            dwell_threshold_s=item.dwell_threshold_s,
            color=item.color,
        )
        db.add(zone)
        new_zones.append(zone)
        redis_payload.append({
            "name": item.name,
            "polygon": item.polygon,
            "restricted": item.restricted,
            "enabled": item.enabled,
            "working_hours_start": item.working_hours_start,
            "working_hours_end": item.working_hours_end,
            "dwell_threshold_s": item.dwell_threshold_s,
            "is_privacy_mask": item.is_privacy_mask,
        })

    await db.flush()

    # Publish to Redis so detection service reloads without restart
    await redis.set(f"nvr:zones:{camera_id}", json.dumps(redis_payload))
    await redis.publish(f"nvr:config:reload:{camera_id}", "1")

    logger.info("zones_replaced", camera_id=camera_id, count=len(new_zones))
    return [_zone_response(z) for z in new_zones]


@router.post("/{camera_id}/zones", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_zone(
    camera_id: str,
    body: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ZoneResponse:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    from datetime import time as dt_time

    def _parse_time(s: str | None):
        if not s:
            return None
        h, m = map(int, s.split(":"))
        return dt_time(h, m)

    zone = DetectionZone(
        camera_id=camera_id,
        name=body.name,
        polygon=body.polygon,
        restricted=body.restricted,
        enabled=body.enabled,
        working_hours_start=_parse_time(body.working_hours_start),
        working_hours_end=_parse_time(body.working_hours_end),
        timezone=body.timezone,
        dwell_threshold_s=body.dwell_threshold_s,
        color=body.color,
    )
    db.add(zone)
    await db.flush()
    return _zone_response(zone)


@router.patch("/{camera_id}/zones/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    camera_id: str,
    zone_id: str,
    body: ZoneUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ZoneResponse:
    result = await db.execute(
        select(DetectionZone).where(
            DetectionZone.id == zone_id, DetectionZone.camera_id == camera_id
        )
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    from datetime import time as dt_time

    def _parse_time(s: str | None):
        if not s:
            return None
        h, m = map(int, s.split(":"))
        return dt_time(h, m)

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "working_hours_start":
            zone.working_hours_start = _parse_time(value)
        elif field == "working_hours_end":
            zone.working_hours_end = _parse_time(value)
        else:
            setattr(zone, field, value)
    return _zone_response(zone)


@router.delete("/{camera_id}/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    camera_id: str,
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(DetectionZone).where(
            DetectionZone.id == zone_id, DetectionZone.camera_id == camera_id
        )
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    await db.delete(zone)


# ── Permissions ────────────────────────────────────────────────────────────────

@router.get("/{camera_id}/permissions", response_model=list[CameraPermissionResponse])
async def list_permissions(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CameraPermissionResponse]:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await db.execute(
        select(CameraPermission).where(CameraPermission.camera_id == camera_id)
    )
    perms = result.scalars().all()
    return [
        CameraPermissionResponse(
            user_id=p.user_id,
            camera_id=p.camera_id,
            can_view_live=p.can_view_live,
            can_view_recordings=p.can_view_recordings,
            can_export_clips=p.can_export_clips,
            can_configure=p.can_configure,
            can_ptz=p.can_ptz,
            granted_at=p.granted_at,
        )
        for p in perms
    ]


@router.patch("/{camera_id}/permissions", response_model=list[CameraPermissionResponse])
async def set_permissions(
    camera_id: str,
    body: list[CameraPermissionSet],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CameraPermissionResponse]:
    try:
        await camera_svc.get_camera(db, camera_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    results = []
    for perm_set in body:
        existing = await db.execute(
            select(CameraPermission).where(
                CameraPermission.camera_id == camera_id,
                CameraPermission.user_id == perm_set.user_id,
            )
        )
        perm = existing.scalar_one_or_none()
        if perm is None:
            perm = CameraPermission(
                camera_id=camera_id,
                user_id=perm_set.user_id,
                granted_by=user.id,
            )
            db.add(perm)
        perm.can_view_live = perm_set.can_view_live
        perm.can_view_recordings = perm_set.can_view_recordings
        perm.can_export_clips = perm_set.can_export_clips
        perm.can_configure = perm_set.can_configure
        perm.can_ptz = perm_set.can_ptz
        await db.flush()
        results.append(CameraPermissionResponse(
            user_id=perm.user_id,
            camera_id=perm.camera_id,
            can_view_live=perm.can_view_live,
            can_view_recordings=perm.can_view_recordings,
            can_export_clips=perm.can_export_clips,
            can_configure=perm.can_configure,
            can_ptz=perm.can_ptz,
            granted_at=perm.granted_at,
        ))
    return results
