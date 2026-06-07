from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit_service as audit_svc
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.models.role import Role
from app.models.user import User
from app.schemas.user import PermissionInfo, RoleCreate, RoleResponse, RoleUpdate

router = APIRouter(prefix="/roles", tags=["roles"])

# All valid permissions in this system
_ALL_PERMISSIONS: list[PermissionInfo] = [
    # Cameras
    PermissionInfo(permission="cameras:view", description="View camera list and live streams", category="cameras"),
    PermissionInfo(permission="cameras:manage", description="Create, update, and delete cameras", category="cameras"),
    PermissionInfo(permission="cameras:configure", description="Change camera settings and detection zones", category="cameras"),
    PermissionInfo(permission="cameras:ptz", description="Control PTZ movement and presets", category="cameras"),
    # Recordings
    PermissionInfo(permission="recordings:view", description="View and search recordings timeline", category="recordings"),
    PermissionInfo(permission="recordings:export", description="Export and download video clips", category="recordings"),
    PermissionInfo(permission="recordings:delete", description="Delete recording segments", category="recordings"),
    # Alerts
    PermissionInfo(permission="alerts:view", description="View alert events and history", category="alerts"),
    PermissionInfo(permission="alerts:manage", description="Create and modify alert rules", category="alerts"),
    PermissionInfo(permission="alerts:acknowledge", description="Acknowledge and resolve alerts", category="alerts"),
    # Notifications
    PermissionInfo(permission="notifications:manage", description="Create and manage notification channels", category="notifications"),
    PermissionInfo(permission="notifications:read", description="View notification channels", category="notifications"),
    # Users
    PermissionInfo(permission="users:manage", description="Create, update, and manage user accounts", category="users"),
    # Roles
    PermissionInfo(permission="roles:manage", description="Create and modify roles and permissions", category="roles"),
    # System
    PermissionInfo(permission="system:admin", description="Full system administration including superadmin role assignment", category="system"),
    PermissionInfo(permission="system:audit", description="View system-wide audit log", category="system"),
    PermissionInfo(permission="system:settings", description="Modify global system settings", category="system"),
]


def _role_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        permissions=role.permissions,
        is_system_role=role.is_system_role,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("/permissions", response_model=list[PermissionInfo])
async def list_permissions(
    _user: User = Depends(require_permission("roles:manage")),
) -> list[PermissionInfo]:
    return _ALL_PERMISSIONS


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("roles:manage")),
) -> list[RoleResponse]:
    result = await db.execute(select(Role).order_by(Role.name))
    return [_role_response(r) for r in result.scalars().all()]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("roles:manage")),
) -> RoleResponse:
    existing = await db.execute(select(Role).where(Role.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Role '{body.name}' already exists")

    valid_perms = {p.permission for p in _ALL_PERMISSIONS}
    invalid = [p for p in body.permissions if p not in valid_perms]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown permissions: {invalid}",
        )

    role = Role(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        permissions=body.permissions,
        is_system_role=False,
    )
    db.add(role)
    await db.flush()
    audit_svc.log(db, "role_created", acting_user, "role", role.id)
    return _role_response(role)


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("roles:manage")),
) -> RoleResponse:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Role {role_id} not found")
    return _role_response(role)


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("roles:manage")),
) -> RoleResponse:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Role {role_id} not found")
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be modified")

    if body.permissions is not None:
        valid_perms = {p.permission for p in _ALL_PERMISSIONS}
        invalid = [p for p in body.permissions if p not in valid_perms]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown permissions: {invalid}",
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(role, field, value)

    audit_svc.log(db, "role_updated", acting_user, "role", role_id)
    return _role_response(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("roles:manage")),
) -> None:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Role {role_id} not found")
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be deleted")

    await db.delete(role)
    audit_svc.log(db, "role_deleted", acting_user, "role", role_id)
