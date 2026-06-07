import mimetypes
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.building import Building
from app.models.camera import Camera
from app.models.camera_placement import CameraPlacement
from app.models.floor import Floor
from app.models.user import User
from app.schemas.building import BuildingCreate, BuildingResponse, BuildingUpdate
from app.schemas.camera_placement import (
    PlacementCameraInfo,
    PlacementCreate,
    PlacementResponse,
    PlacementUpdate,
)
from app.schemas.floor import FloorCreate, FloorResponse, FloorUpdate

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/floor-plan", tags=["floor-plan"])

FLOOR_PLANS_DIR = Path("/data/floor_plans")
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


def _building_response(b: Building) -> BuildingResponse:
    return BuildingResponse(
        id=b.id,
        name=b.name,
        description=b.description,
        address=b.address,
        created_at=b.created_at,
        updated_at=b.updated_at,
        floor_count=len(b.floors) if b.floors is not None else 0,
    )


def _floor_response(f: Floor) -> FloorResponse:
    return FloorResponse(
        id=f.id,
        building_id=f.building_id,
        name=f.name,
        level=f.level,
        has_image=f.plan_image_path is not None,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _placement_response(p: CameraPlacement) -> PlacementResponse:
    cam = p.camera
    return PlacementResponse(
        id=p.id,
        floor_id=p.floor_id,
        camera_id=p.camera_id,
        x=p.x,
        y=p.y,
        rotation=p.rotation,
        created_at=p.created_at,
        camera=PlacementCameraInfo(
            id=cam.id,
            name=cam.name,
            location=cam.location or "",
            status=cam.status.value if hasattr(cam.status, "value") else str(cam.status),
            ip_address=cam.ip_address,
        ),
    )


# ── Buildings ─────────────────────────────────────────────────────────────────

@router.get("/buildings", response_model=list[BuildingResponse])
async def list_buildings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[BuildingResponse]:
    result = await db.execute(
        select(Building).options(selectinload(Building.floors)).order_by(Building.name)
    )
    return [_building_response(b) for b in result.scalars()]


@router.post("/buildings", response_model=BuildingResponse, status_code=status.HTTP_201_CREATED)
async def create_building(
    body: BuildingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BuildingResponse:
    b = Building(name=body.name, description=body.description, address=body.address)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    logger.info("building_created", id=b.id, name=b.name, actor=user.email)
    b.floors = []
    return _building_response(b)


@router.get("/buildings/{building_id}", response_model=BuildingResponse)
async def get_building(
    building_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BuildingResponse:
    result = await db.execute(
        select(Building).options(selectinload(Building.floors)).where(Building.id == building_id)
    )
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Building not found")
    return _building_response(b)


@router.patch("/buildings/{building_id}", response_model=BuildingResponse)
async def update_building(
    building_id: str,
    body: BuildingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BuildingResponse:
    result = await db.execute(
        select(Building).options(selectinload(Building.floors)).where(Building.id == building_id)
    )
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Building not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(b, field, value)
    await db.commit()
    await db.refresh(b)
    logger.info("building_updated", id=b.id, actor=user.email)
    return _building_response(b)


@router.delete("/buildings/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_building(
    building_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    b = await db.get(Building, building_id)
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Building not found")
    await db.delete(b)
    await db.commit()
    logger.info("building_deleted", id=building_id, actor=user.email)


# ── Floors ────────────────────────────────────────────────────────────────────

@router.get("/buildings/{building_id}/floors", response_model=list[FloorResponse])
async def list_floors(
    building_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[FloorResponse]:
    b = await db.get(Building, building_id)
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Building not found")
    result = await db.execute(
        select(Floor).where(Floor.building_id == building_id).order_by(Floor.level, Floor.name)
    )
    return [_floor_response(f) for f in result.scalars()]


@router.post(
    "/buildings/{building_id}/floors",
    response_model=FloorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_floor(
    building_id: str,
    body: FloorCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FloorResponse:
    b = await db.get(Building, building_id)
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Building not found")
    f = Floor(building_id=building_id, name=body.name, level=body.level)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    logger.info("floor_created", id=f.id, name=f.name, building_id=building_id, actor=user.email)
    return _floor_response(f)


@router.get("/floors/{floor_id}", response_model=FloorResponse)
async def get_floor(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FloorResponse:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    return _floor_response(f)


@router.patch("/floors/{floor_id}", response_model=FloorResponse)
async def update_floor(
    floor_id: str,
    body: FloorUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FloorResponse:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(f, field, value)
    await db.commit()
    await db.refresh(f)
    logger.info("floor_updated", id=f.id, actor=user.email)
    return _floor_response(f)


@router.delete("/floors/{floor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_floor(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    if f.plan_image_path:
        _safe_delete_image(f.plan_image_path)
    await db.delete(f)
    await db.commit()
    logger.info("floor_deleted", id=floor_id, actor=user.email)


# ── Floor plan image ──────────────────────────────────────────────────────────

def _safe_image_path(filename: str) -> Path:
    path = (FLOOR_PLANS_DIR / filename).resolve()
    if not str(path).startswith(str(FLOOR_PLANS_DIR.resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    return path


def _safe_delete_image(filename: str) -> None:
    try:
        _safe_image_path(filename).unlink(missing_ok=True)
    except Exception:
        pass


@router.post("/floors/{floor_id}/image", response_model=FloorResponse)
async def upload_floor_image(
    floor_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FloorResponse:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, WebP, and GIF images are accepted",
        )

    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large (max 20 MB)",
        )

    ext = mimetypes.guess_extension(content_type) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"{floor_id}{ext}"

    FLOOR_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _safe_image_path(filename)

    if f.plan_image_path and f.plan_image_path != filename:
        _safe_delete_image(f.plan_image_path)

    dest.write_bytes(data)
    f.plan_image_path = filename
    await db.commit()
    await db.refresh(f)
    logger.info("floor_image_uploaded", floor_id=floor_id, filename=filename, actor=user.email)
    return _floor_response(f)


@router.get("/floors/{floor_id}/image")
async def get_floor_image(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    f = await db.get(Floor, floor_id)
    if not f or not f.plan_image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No image for this floor")
    path = _safe_image_path(f.plan_image_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


# ── Placements ────────────────────────────────────────────────────────────────

@router.get("/floors/{floor_id}/placements", response_model=list[PlacementResponse])
async def list_placements(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PlacementResponse]:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    result = await db.execute(
        select(CameraPlacement)
        .options(selectinload(CameraPlacement.camera))
        .where(CameraPlacement.floor_id == floor_id)
    )
    return [_placement_response(p) for p in result.scalars()]


@router.post(
    "/floors/{floor_id}/placements",
    response_model=PlacementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_placement(
    floor_id: str,
    body: PlacementCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlacementResponse:
    f = await db.get(Floor, floor_id)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    cam = await db.get(Camera, body.camera_id)
    if not cam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    existing = await db.execute(
        select(CameraPlacement).where(CameraPlacement.camera_id == body.camera_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Camera is already placed on a floor",
        )

    p = CameraPlacement(
        floor_id=floor_id,
        camera_id=body.camera_id,
        x=body.x,
        y=body.y,
        rotation=body.rotation,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    result = await db.execute(
        select(CameraPlacement)
        .options(selectinload(CameraPlacement.camera))
        .where(CameraPlacement.id == p.id)
    )
    p = result.scalar_one()
    logger.info("camera_placed", placement_id=p.id, camera_id=body.camera_id, floor_id=floor_id, actor=user.email)
    return _placement_response(p)


@router.patch("/placements/{placement_id}", response_model=PlacementResponse)
async def update_placement(
    placement_id: str,
    body: PlacementUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlacementResponse:
    result = await db.execute(
        select(CameraPlacement)
        .options(selectinload(CameraPlacement.camera))
        .where(CameraPlacement.id == placement_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    await db.commit()
    await db.refresh(p)
    result2 = await db.execute(
        select(CameraPlacement)
        .options(selectinload(CameraPlacement.camera))
        .where(CameraPlacement.id == placement_id)
    )
    p = result2.scalar_one()
    return _placement_response(p)


@router.delete("/placements/{placement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_placement(
    placement_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    p = await db.get(CameraPlacement, placement_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement not found")
    await db.delete(p)
    await db.commit()
    logger.info("camera_unplaced", placement_id=placement_id, actor=user.email)
