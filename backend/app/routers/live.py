"""
Live view routes — HLS stream management and snapshots.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.models.camera import Camera
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/live", tags=["live"])


async def _load_camera(db: AsyncSession, camera_id: str) -> Camera:
    import uuid
    try:
        uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Camera {camera_id} not found")
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.is_deleted.is_(False))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Camera {camera_id} not found")
    return camera


@router.get("/{camera_id}/stream-url")
async def get_stream_url(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    camera = await _load_camera(db, camera_id)

    hls_manager = getattr(request.app.state, "hls_manager", None)
    if hls_manager is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="HLS manager not available")

    try:
        hls_path = await hls_manager.start_stream(camera)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    base_url = f"{scheme}://{host}"

    return {
        "hls_url": f"{base_url}{hls_path}",
        "camera_id": camera.id,
        "camera_name": camera.name,
        "status": camera.status.value,
    }


@router.delete("/{camera_id}/stream", status_code=status.HTTP_204_NO_CONTENT)
async def force_stop_stream(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("cameras:manage")),
) -> None:
    await _load_camera(db, camera_id)
    hls_manager = getattr(request.app.state, "hls_manager", None)
    if hls_manager:
        await hls_manager.stop_stream(camera_id)


@router.get("/active")
async def list_active_streams(
    request: Request,
    _user: User = Depends(require_permission("cameras:manage")),
) -> dict:
    hls_manager = getattr(request.app.state, "hls_manager", None)
    if hls_manager is None:
        return {"streams": {}}
    return {"streams": await hls_manager.get_status()}


@router.get("/{camera_id}/snapshot")
async def get_snapshot(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    from app.services.onvif_service import get_snapshot as onvif_snapshot

    camera = await _load_camera(db, camera_id)
    try:
        jpeg_bytes = await onvif_snapshot(camera)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Snapshot unavailable: {exc}",
        ) from exc
    return Response(content=jpeg_bytes, media_type="image/jpeg")
