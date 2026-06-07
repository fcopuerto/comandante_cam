import shutil
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.models.storage_target import StorageTarget
from app.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/storage/targets", tags=["storage"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class StorageTargetCreate(BaseModel):
    name: str
    target_type: str  # nfs, smb, local
    host: str | None = None
    export_path: str
    mount_point: str
    mount_options: str | None = None


class StorageTargetUpdate(BaseModel):
    name: str | None = None
    mount_options: str | None = None


class StorageTargetResponse(BaseModel):
    id: str
    name: str
    target_type: str
    host: str | None
    export_path: str
    mount_point: str
    mount_options: str | None
    is_active: bool
    created_at: str
    # Runtime status (not stored in DB)
    mounted: bool
    writable: bool
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    usage_percent: float | None
    fstab_line: str


def _check_mount(mount_point: str) -> bool:
    """Return True if mount_point is a currently mounted filesystem."""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mount_point:
                    return True
    except OSError:
        pass
    return False


def _check_writable(mount_point: str) -> bool:
    try:
        test_file = Path(mount_point) / ".nvr_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except OSError:
        return False


def _disk_usage(mount_point: str) -> tuple[int, int, int, float] | None:
    try:
        u = shutil.disk_usage(mount_point)
        pct = round(u.used / u.total * 100, 1) if u.total else 0.0
        return u.total, u.used, u.free, pct
    except OSError:
        return None


def _fstab_line(t: StorageTarget) -> str:
    opts = t.mount_options or "rw,async,hard,intr,rsize=131072,wsize=131072,_netdev"
    if t.target_type == "nfs":
        src = f"{t.host}:{t.export_path}"
        return f"{src} {t.mount_point} nfs {opts} 0 0"
    if t.target_type == "smb":
        src = f"//{t.host}{t.export_path}"
        return f"{src} {t.mount_point} cifs {opts} 0 0"
    return f"{t.export_path} {t.mount_point} none bind 0 0"


def _enrich(t: StorageTarget) -> StorageTargetResponse:
    mounted = _check_mount(t.mount_point)
    writable = _check_writable(t.mount_point) if mounted else False
    usage = _disk_usage(t.mount_point) if mounted else None
    total, used, free, pct = usage if usage else (None, None, None, None)
    return StorageTargetResponse(
        id=t.id,
        name=t.name,
        target_type=t.target_type,
        host=t.host,
        export_path=t.export_path,
        mount_point=t.mount_point,
        mount_options=t.mount_options,
        is_active=t.is_active,
        created_at=t.created_at.isoformat(),
        mounted=mounted,
        writable=writable,
        total_bytes=total,
        used_bytes=used,
        free_bytes=free,
        usage_percent=pct,
        fstab_line=_fstab_line(t),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[StorageTargetResponse])
async def list_storage_targets(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[StorageTargetResponse]:
    result = await db.execute(select(StorageTarget).order_by(StorageTarget.created_at))
    return [_enrich(t) for t in result.scalars().all()]


@router.post("", response_model=StorageTargetResponse)
async def create_storage_target(
    body: StorageTargetCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:read")),
) -> StorageTargetResponse:
    if body.target_type not in ("nfs", "smb", "local"):
        raise HTTPException(status_code=422, detail="target_type must be nfs, smb, or local")
    if body.target_type in ("nfs", "smb") and not body.host:
        raise HTTPException(status_code=422, detail="host is required for nfs and smb targets")

    target = StorageTarget(
        name=body.name,
        target_type=body.target_type,
        host=body.host,
        export_path=body.export_path,
        mount_point=body.mount_point,
        mount_options=body.mount_options,
        is_active=False,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    logger.info("storage_target_created", id=target.id, name=target.name)
    return _enrich(target)


@router.put("/{target_id}", response_model=StorageTargetResponse)
async def update_storage_target(
    target_id: str,
    body: StorageTargetUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:read")),
) -> StorageTargetResponse:
    result = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Storage target not found")
    if body.name is not None:
        target.name = body.name
    if body.mount_options is not None:
        target.mount_options = body.mount_options
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target)
    return _enrich(target)


@router.delete("/{target_id}", status_code=204)
async def delete_storage_target(
    target_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:read")),
) -> None:
    result = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Storage target not found")
    if target.is_active:
        raise HTTPException(status_code=409, detail="Cannot delete the active storage target")
    await db.delete(target)
    await db.commit()
    logger.info("storage_target_deleted", id=target_id)


@router.post("/{target_id}/activate", response_model=StorageTargetResponse)
async def activate_storage_target(
    target_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("system:read")),
) -> StorageTargetResponse:
    result = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Storage target not found")
    if not _check_mount(target.mount_point):
        raise HTTPException(status_code=409, detail=f"Mount point {target.mount_point} is not currently mounted")

    # Deactivate all, then activate this one
    await db.execute(update(StorageTarget).values(is_active=False))
    target.is_active = True
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target)
    logger.info("storage_target_activated", id=target_id, name=target.name)
    return _enrich(target)
