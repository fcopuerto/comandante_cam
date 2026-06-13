"""
System-level routes: health, storage, events, audit log, and Prometheus metrics.
"""
import asyncio
import csv
import io
import shutil
from math import ceil
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.redis_client import get_redis
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.system_event import SystemEvent
from app.models.user import User
from app.schemas.camera import Page
from app.schemas.user import AuditLogResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

# ---------------------------------------------------------------------------
# Prometheus metric definitions — single registry, created once at import time.
# ---------------------------------------------------------------------------

_REGISTRY = CollectorRegistry(auto_describe=True)

nvr_alerts_total = Counter(
    "nvr_alerts_total",
    "Total alert events ever recorded",
    registry=_REGISTRY,
)
nvr_login_attempts_total = Counter(
    "nvr_login_attempts_total",
    "Total login attempts (successful + failed)",
    registry=_REGISTRY,
)
nvr_login_failures_total = Counter(
    "nvr_login_failures_total",
    "Total failed login attempts",
    registry=_REGISTRY,
)

nvr_cameras_online = Gauge(
    "nvr_cameras_online",
    "Number of cameras currently in online or recording status",
    registry=_REGISTRY,
)
nvr_cameras_recording = Gauge(
    "nvr_cameras_recording",
    "Number of cameras currently in recording status",
    registry=_REGISTRY,
)
nvr_hls_streams_active = Gauge(
    "nvr_hls_streams_active",
    "Number of active HLS stream processes",
    registry=_REGISTRY,
)
nvr_ws_connections_active = Gauge(
    "nvr_ws_connections_active",
    "Number of active WebSocket connections",
    registry=_REGISTRY,
)


# ── Health ────────────────────────────────────────────────────────────────────

class SystemHealthResponse(BaseModel):
    database: bool
    redis: bool
    celery: bool
    detection: bool
    storage_warning: bool
    storage_critical: bool


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SystemHealthResponse:
    settings = get_settings()

    # Database
    db_ok = False
    try:
        from sqlalchemy import text as sa_text
        await db.execute(sa_text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # Redis
    redis_ok = False
    try:
        from redis.asyncio import from_url as redis_from_url
        r = redis_from_url(settings.REDIS_URL)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        redis_ok = True
    except Exception:
        pass

    # Celery — check workers via Redis broker inspect ping key
    celery_ok = False
    try:
        from redis.asyncio import from_url as redis_from_url
        r = redis_from_url(settings.CELERY_BROKER_URL)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        celery_ok = True
    except Exception:
        pass

    # Detection service — HTTP health endpoint on port 8001
    detection_ok = False
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await asyncio.wait_for(
                client.get("http://detection:8001/health"), timeout=2.0
            )
            detection_ok = resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        pass

    # Storage thresholds
    storage_warning = False
    storage_critical = False
    try:
        usage = shutil.disk_usage(settings.STORAGE_PATH)
        pct = (usage.used / usage.total) * 100
        storage_warning = pct >= settings.STORAGE_WARNING_PCT
        storage_critical = pct >= settings.STORAGE_CRITICAL_PCT
    except Exception:
        pass

    return SystemHealthResponse(
        database=db_ok,
        redis=redis_ok,
        celery=celery_ok,
        detection=detection_ok,
        storage_warning=storage_warning,
        storage_critical=storage_critical,
    )


# ── Detection service control ─────────────────────────────────────────────────

class DetectionStatusResponse(BaseModel):
    container_state: str          # running / stopped / not_found / unknown
    healthy: bool                 # HTTP health check passed
    last_heartbeat: str | None    # ISO timestamp of last successful check, or None
    heartbeat_age_seconds: int | None
    cameras_active: int | None    # from detection /health response


@router.get("/detection/status", response_model=DetectionStatusResponse)
async def detection_status(
    _user: User = Depends(get_current_user),
) -> DetectionStatusResponse:
    settings = get_settings()

    # Detection HTTP health check
    last_heartbeat: str | None = None
    heartbeat_age: int | None = None
    healthy = False
    detection_detail: dict = {}
    try:
        import httpx
        from datetime import datetime, timezone
        async with httpx.AsyncClient() as client:
            resp = await asyncio.wait_for(
                client.get("http://detection:8001/health"), timeout=2.0
            )
            if resp.status_code == 200:
                detection_detail = resp.json()
                healthy = detection_detail.get("status") == "ok"
                last_heartbeat = datetime.now(timezone.utc).isoformat()
                heartbeat_age = 0
    except Exception:
        pass

    # Docker container state
    container_state = "unknown"
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": "com.docker.compose.service=detection"},
        )
        if containers:
            container_state = containers[0].status  # running / exited / paused / etc.
        else:
            container_state = "not_found"
        client.close()
    except Exception:
        pass

    return DetectionStatusResponse(
        container_state=container_state,
        healthy=healthy,
        last_heartbeat=last_heartbeat,
        heartbeat_age_seconds=heartbeat_age,
        cameras_active=detection_detail.get("cameras"),
    )


class DetectionRestartResponse(BaseModel):
    status: str
    container_name: str


async def _publish_cameras_to_redis(db: AsyncSession, redis) -> int:
    """Write active camera RTSP configs to nvr:cameras Redis key for detection service."""
    import json
    from app.utils.encryption import get_encryption

    result = await db.execute(
        select(Camera).where(Camera.is_deleted.is_(False))
    )
    cameras = result.scalars().all()
    enc = get_encryption()
    payload = []
    for cam in cameras:
        rtsp_url = cam.rtsp_main_url or cam.rtsp_sub_url
        if not rtsp_url:
            continue
        # Substitute credentials into RTSP URL if needed
        if cam.username and cam.password_encrypted:
            password = enc.decrypt(cam.password_encrypted)
            # Insert credentials if not already in URL
            if "@" not in rtsp_url.split("://", 1)[-1]:
                proto, rest = rtsp_url.split("://", 1)
                rtsp_url = f"{proto}://{cam.username}:{password}@{rest}"
        payload.append({"id": str(cam.id), "rtsp_url": rtsp_url})
    await redis.set("nvr:cameras", json.dumps(payload))
    return len(payload)


@router.post("/detection/restart", response_model=DetectionRestartResponse)
async def restart_detection(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(require_permission("system:read")),
) -> DetectionRestartResponse:
    # Publish current camera configs to Redis before restart
    cam_count = await _publish_cameras_to_redis(db, redis)
    logger.info("cameras_published_to_redis", count=cam_count)

    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": "com.docker.compose.service=detection"},
        )
        if not containers:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Detection container not found")
        container = containers[0]
        container.restart(timeout=10)
        name = container.name
        client.close()
        logger.info("detection_restarted", container=name)
        return DetectionRestartResponse(status="restarted", container_name=name)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(exc))


# ── Celery worker control ─────────────────────────────────────────────────────

class WorkerStatusResponse(BaseModel):
    online: bool
    worker_name: str | None
    active_tasks: int
    recording_count: int
    alert_consumer_running: bool
    container_state: str  # running / exited / not_found / unknown


@router.get("/workers/status", response_model=WorkerStatusResponse)
async def workers_status(
    _user: User = Depends(get_current_user),
) -> WorkerStatusResponse:
    container_state = "unknown"
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": "com.docker.compose.service=worker"},
        )
        container_state = containers[0].status if containers else "not_found"
        client.close()
    except Exception:
        pass

    active_tasks = 0
    recording_count = 0
    alert_consumer_running = False
    online = False
    worker_name: str | None = None

    def _sync_inspect():
        from app.celery_app import celery_app
        return celery_app.control.inspect(timeout=2.0).active()

    try:
        loop = asyncio.get_event_loop()
        active_map = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_inspect),
            timeout=4.0,
        )
        if active_map:
            online = True
            for wid, tasks in active_map.items():
                if worker_name is None:
                    worker_name = wid
                active_tasks += len(tasks)
                for task in tasks:
                    name = task.get("name", "")
                    if "start_recording" in name:
                        recording_count += 1
                    if "consume_alerts" in name:
                        alert_consumer_running = True
    except Exception:
        pass

    return WorkerStatusResponse(
        online=online,
        worker_name=worker_name,
        active_tasks=active_tasks,
        recording_count=recording_count,
        alert_consumer_running=alert_consumer_running,
        container_state=container_state,
    )


class WorkerRestartResponse(BaseModel):
    status: str
    container_name: str


@router.post("/workers/restart", response_model=WorkerRestartResponse)
async def restart_worker(
    _user: User = Depends(require_permission("system:read")),
) -> WorkerRestartResponse:
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": "com.docker.compose.service=worker"},
        )
        if not containers:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Worker container not found")
        container = containers[0]
        container.restart(timeout=10)
        name = container.name
        client.close()
        logger.info("worker_restarted", container=name)
        return WorkerRestartResponse(status="restarted", container_name=name)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(exc))


# ── Storage ───────────────────────────────────────────────────────────────────

class PerCameraStorage(BaseModel):
    camera_id: str
    camera_name: str
    used_bytes: int


class StorageStatusResponse(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    per_camera: list[PerCameraStorage]


@router.get("/storage", response_model=StorageStatusResponse)
async def storage_status(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StorageStatusResponse:
    settings = get_settings()

    total_bytes = 0
    used_bytes = 0
    free_bytes = 0
    try:
        usage = shutil.disk_usage(settings.STORAGE_PATH)
        total_bytes = usage.total
        used_bytes = usage.used
        free_bytes = usage.free
    except Exception:
        pass

    usage_percent = round((used_bytes / total_bytes * 100), 2) if total_bytes else 0.0

    # Per-camera disk usage by walking recording dirs
    cameras_result = await db.execute(
        select(Camera.id, Camera.name).where(Camera.is_deleted.is_(False))
    )
    camera_map = {row.id: row.name for row in cameras_result.all()}

    per_camera: list[PerCameraStorage] = []
    storage_path = Path(settings.STORAGE_PATH)
    if storage_path.exists():
        for cam_dir in storage_path.iterdir():
            if not cam_dir.is_dir():
                continue
            cam_id = cam_dir.name
            cam_bytes = sum(f.stat().st_size for f in cam_dir.rglob("*") if f.is_file())
            if cam_bytes > 0:
                per_camera.append(PerCameraStorage(
                    camera_id=cam_id,
                    camera_name=camera_map.get(cam_id, cam_id),
                    used_bytes=cam_bytes,
                ))

    per_camera.sort(key=lambda x: x.used_bytes, reverse=True)

    return StorageStatusResponse(
        total_bytes=total_bytes,
        used_bytes=used_bytes,
        free_bytes=free_bytes,
        usage_percent=usage_percent,
        per_camera=per_camera,
    )


# ── Application settings (Redis-backed, no DB migration needed) ───────────────

_SETTINGS_KEY = "nvr:settings:app"

_SETTINGS_DEFAULTS: dict = {
    "retention_days_default": 30,
    "session_timeout_minutes": 1440,
    "mfa_enforcement": False,
    "watermark_exports": False,
    "max_export_size_gb": 10,
    "storage_warning_threshold": 75,
    "storage_critical_threshold": 90,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_starttls": True,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
}


class AppSettingsResponse(BaseModel):
    retention_days_default: int
    session_timeout_minutes: int
    mfa_enforcement: bool
    watermark_exports: bool
    max_export_size_gb: int
    storage_warning_threshold: int
    storage_critical_threshold: int
    smtp_host: str
    smtp_port: int
    smtp_starttls: bool
    smtp_user: str
    smtp_password: str
    smtp_from: str


class AppSettingsPatch(BaseModel):
    retention_days_default: int | None = None
    session_timeout_minutes: int | None = None
    mfa_enforcement: bool | None = None
    watermark_exports: bool | None = None
    max_export_size_gb: int | None = None
    storage_warning_threshold: int | None = None
    storage_critical_threshold: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_starttls: bool | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


async def _load_settings(redis) -> dict:
    import json
    raw = await redis.get(_SETTINGS_KEY)
    stored = json.loads(raw) if raw else {}
    return {**_SETTINGS_DEFAULTS, **stored}


@router.get("/settings", response_model=AppSettingsResponse)
async def get_app_settings(
    _user: User = Depends(require_permission("system:admin")),
    redis=Depends(get_redis),
) -> AppSettingsResponse:
    data = await _load_settings(redis)
    return AppSettingsResponse(**data)


@router.patch("/settings", response_model=AppSettingsResponse)
async def patch_app_settings(
    body: AppSettingsPatch,
    _user: User = Depends(require_permission("system:admin")),
    redis=Depends(get_redis),
) -> AppSettingsResponse:
    import json
    current = await _load_settings(redis)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    current.update(updates)
    await redis.set(_SETTINGS_KEY, json.dumps(current))
    return AppSettingsResponse(**current)


class SmtpTestRequest(BaseModel):
    to: str


@router.post("/smtp/test")
async def test_smtp(
    body: SmtpTestRequest,
    _user: User = Depends(require_permission("system:admin")),
) -> dict:
    from fastapi import HTTPException
    import smtplib
    from email.mime.text import MIMEText
    from app.services.notification_service import _get_smtp_config

    cfg = _get_smtp_config()
    if not cfg["host"]:
        raise HTTPException(status_code=400, detail="SMTP host is not configured")

    msg = MIMEText("This is a test email from NVR Pro to confirm your SMTP settings are working.", "plain")
    msg["Subject"] = "NVR Pro — SMTP test"
    msg["From"] = cfg["from"] or cfg["user"]
    msg["To"] = body.to

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            if cfg["starttls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(msg["From"], [body.to], msg.as_string())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"ok": True}


# ── System events ─────────────────────────────────────────────────────────────

class SystemEventResponse(BaseModel):
    id: str
    level: str
    message: str
    details: dict | None
    created_at: str


class SystemEventsPage(BaseModel):
    items: list[SystemEventResponse]
    total: int
    page: int
    page_size: int
    pages: int


@router.get("/events", response_model=SystemEventsPage)
async def system_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SystemEventsPage:
    total_result = await db.execute(select(func.count()).select_from(SystemEvent))
    total = total_result.scalar_one()

    result = await db.execute(
        select(SystemEvent)
        .order_by(desc(SystemEvent.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = result.scalars().all()

    return SystemEventsPage(
        items=[
            SystemEventResponse(
                id=str(e.id),
                level=e.severity or "info",
                message=e.message or "",
                details=e.detail,
                created_at=e.created_at.isoformat(),
            )
            for e in events
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 1,
    )


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=Page[AuditLogResponse])
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:audit")),
) -> Page[AuditLogResponse]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if severity:
        stmt = stmt.where(AuditLog.severity == severity)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    entries = result.scalars().all()
    items = [
        AuditLogResponse(
            id=e.id,
            user_id=e.user_id,
            user_email=e.user_email,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            detail=e.detail,
            ip_address=e.ip_address,
            request_id=e.request_id,
            severity=e.severity,
            created_at=e.created_at,
        )
        for e in entries
    ]
    return Page(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/audit-log/export", response_class=StreamingResponse)
async def export_audit_log_csv(
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:audit")),
) -> StreamingResponse:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if severity:
        stmt = stmt.where(AuditLog.severity == severity)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    result = await db.execute(stmt.order_by(AuditLog.created_at.desc()))
    entries = result.scalars().all()

    def _generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "created_at", "user_id", "user_email", "action",
            "resource_type", "resource_id", "severity", "ip_address", "request_id",
        ])
        buf.seek(0)
        yield buf.read()
        for e in entries:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                e.id, e.created_at.isoformat(), e.user_id, e.user_email,
                e.action, e.resource_type, e.resource_id, e.severity,
                e.ip_address, e.request_id,
            ])
            buf.seek(0)
            yield buf.read()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
_ALLOWED_SCRAPE_HOSTS = {"127.0.0.1", "::1"}


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Prometheus scrape endpoint — restricted to localhost.
    Returns current gauge readings derived from live DB queries and app state.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in _ALLOWED_SCRAPE_HOSTS:
        return Response(status_code=403, content="Forbidden")

    from app.core.constants import CameraStatus
    from app.models.alert_event import AlertEvent

    # --- Counters: derive from audit_log and alert_events tables on each scrape.
    # nvr_alerts_total — total alert events ever created.
    alerts_result = await db.execute(select(func.count()).select_from(AlertEvent))
    alerts_count = alerts_result.scalar_one()

    # nvr_login_attempts_total / nvr_login_failures_total — from audit_log actions.
    login_attempts_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["login_success", "login_failed", "login_locked"])
        )
    )
    login_attempts_count = login_attempts_result.scalar_one()

    login_failures_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["login_failed", "login_locked"])
        )
    )
    login_failures_count = login_failures_result.scalar_one()

    # Reset counters to the absolute DB-derived values on every scrape so that
    # the exported value always matches reality (counters are treated as gauges
    # here because we materialise the full count each time).
    # prometheus_client Counters only go up; we work around monotonicity by
    # always incrementing by the delta since our local baseline.
    _sync_counter(nvr_alerts_total, alerts_count)
    _sync_counter(nvr_login_attempts_total, login_attempts_count)
    _sync_counter(nvr_login_failures_total, login_failures_count)

    # --- Gauges: cameras online / recording.
    online_statuses = {CameraStatus.online, CameraStatus.recording}
    cameras_result = await db.execute(
        select(Camera.status).where(Camera.is_deleted.is_(False))
    )
    camera_statuses = [row.status for row in cameras_result.all()]
    online_count = sum(1 for s in camera_statuses if s in online_statuses)
    recording_count = sum(1 for s in camera_statuses if s == CameraStatus.recording)

    nvr_cameras_online.set(online_count)
    nvr_cameras_recording.set(recording_count)

    # --- Gauges: HLS streams and WebSocket connections from app state.
    hls_manager = getattr(request.app.state, "hls_manager", None)
    hls_active = len(hls_manager._streams) if hls_manager is not None else 0
    nvr_hls_streams_active.set(hls_active)

    ws_count = getattr(request.app.state, "ws_connection_count", 0)
    nvr_ws_connections_active.set(ws_count)

    return Response(
        content=generate_latest(_REGISTRY),
        media_type=_PROMETHEUS_CONTENT_TYPE,
    )


# Internal counter-sync helper — prometheus_client Counters are strictly
# monotonic, so we track the last exported value and increment by delta only.
_counter_baseline: dict[str, float] = {}


def _sync_counter(counter: Counter, absolute_value: float) -> None:
    name = counter._name  # type: ignore[attr-defined]
    baseline = _counter_baseline.get(name, 0.0)
    delta = absolute_value - baseline
    if delta > 0:
        counter.inc(delta)
        _counter_baseline[name] = absolute_value
