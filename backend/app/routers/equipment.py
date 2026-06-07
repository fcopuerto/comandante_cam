from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentResponse, EquipmentUpdate
from app.utils.encryption import get_encryption

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/equipment", tags=["equipment"])


def _to_response(eq: Equipment) -> EquipmentResponse:
    return EquipmentResponse(
        id=eq.id,
        name=eq.name,
        ip_address=eq.ip_address,
        ssh_port=eq.ssh_port,
        ssh_user=eq.ssh_user,
        has_ssh_password=eq.ssh_password_enc is not None,
        ssh_key_path=eq.ssh_key_path,
        device_type=eq.device_type,
        location=eq.location,
        notes=eq.notes,
        is_active=eq.is_active,
        created_at=eq.created_at,
        updated_at=eq.updated_at,
    )


@router.get("", response_model=list[EquipmentResponse])
async def list_equipment(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[EquipmentResponse]:
    result = await db.execute(select(Equipment).order_by(Equipment.name))
    return [_to_response(eq) for eq in result.scalars()]


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    body: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EquipmentResponse:
    enc = get_encryption()
    eq = Equipment(
        name=body.name,
        ip_address=body.ip_address,
        ssh_port=body.ssh_port,
        ssh_user=body.ssh_user,
        ssh_password_enc=enc.encrypt(body.ssh_password) if body.ssh_password else None,
        ssh_key_path=body.ssh_key_path,
        device_type=body.device_type,
        location=body.location,
        notes=body.notes,
    )
    db.add(eq)
    await db.commit()
    await db.refresh(eq)
    logger.info("equipment_created", id=eq.id, name=eq.name, type=eq.device_type, actor=user.email)
    return _to_response(eq)


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EquipmentResponse:
    eq = await db.get(Equipment, equipment_id)
    if not eq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    return _to_response(eq)


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: str,
    body: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EquipmentResponse:
    eq = await db.get(Equipment, equipment_id)
    if not eq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    enc = get_encryption()
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "ssh_password":
            eq.ssh_password_enc = enc.encrypt(value) if value else None
        else:
            setattr(eq, field, value)
    await db.commit()
    await db.refresh(eq)
    logger.info("equipment_updated", id=eq.id, actor=user.email)
    return _to_response(eq)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    eq = await db.get(Equipment, equipment_id)
    if not eq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    await db.delete(eq)
    await db.commit()
    logger.info("equipment_deleted", id=equipment_id, actor=user.email)
