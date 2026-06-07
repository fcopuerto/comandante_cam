"""
Role service — default role seeding and role management helpers.
"""
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role

logger = structlog.get_logger(__name__)

# Default roles seeded on first startup. Permissions follow the pattern
# <resource>:<action> as documented in SPEC.md.
_DEFAULT_ROLES: list[dict] = [
    {
        "name": "superadmin",
        "display_name": "Super Administrator",
        "description": "Full unrestricted access to all system functions.",
        "permissions": ["system:admin"],
        "is_system_role": True,
    },
    {
        "name": "admin",
        "display_name": "Administrator",
        "description": "Administrative access excluding MFA bypass and audit purge.",
        "permissions": [
            "cameras:read", "cameras:write", "cameras:delete",
            "recordings:read", "recordings:export",
            "alerts:read", "alerts:write", "alerts:acknowledge",
            "users:read", "users:write",
            "roles:read",
            "system:audit",
            "live:view",
        ],
        "is_system_role": True,
    },
    {
        "name": "operator",
        "display_name": "Operator",
        "description": "Day-to-day monitoring: live view, recording access, alert acknowledgement.",
        "permissions": [
            "cameras:read",
            "recordings:read", "recordings:export",
            "alerts:read", "alerts:acknowledge",
            "live:view",
        ],
        "is_system_role": True,
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to cameras and recordings.",
        "permissions": [
            "cameras:read",
            "recordings:read",
            "alerts:read",
            "live:view",
        ],
        "is_system_role": True,
    },
]


async def seed_roles_if_empty(db: AsyncSession) -> None:
    """Insert default roles when the roles table is empty (idempotent)."""
    count_result = await db.execute(select(func.count()).select_from(Role))
    count = count_result.scalar_one()
    if count > 0:
        return

    for role_data in _DEFAULT_ROLES:
        role = Role(
            name=role_data["name"],
            display_name=role_data["display_name"],
            description=role_data["description"],
            permissions=role_data["permissions"],
            is_system_role=role_data["is_system_role"],
        )
        db.add(role)

    await db.commit()
    logger.info("roles_seeded", count=len(_DEFAULT_ROLES))
