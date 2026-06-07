"""
Idempotent seed script: creates the 6 default system roles and, if no users
exist, creates an initial superadmin user.

Run inside the backend container:
    docker compose exec backend python scripts/seed_roles.py
"""
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.role import Role
from app.models.user import User

ALL_PERMISSIONS = [
    "system:admin",
    "system:audit",
    "cameras:view_live",
    "cameras:manage",
    "recordings:view",
    "recordings:export",
    "recordings:delete",
    "alerts:view",
    "alerts:acknowledge",
    "alerts:manage",
    "notifications:read",
    "notifications:manage",
    "users:manage",
    "roles:manage",
]

ROLES = [
    {
        "name": "superadmin",
        "display_name": "Super Administrator",
        "description": "Full system access including system administration.",
        "permissions": ALL_PERMISSIONS,
        "is_system_role": True,
    },
    {
        "name": "admin",
        "display_name": "Administrator",
        "description": "Full access excluding system administration.",
        "permissions": [p for p in ALL_PERMISSIONS if p != "system:admin"],
        "is_system_role": True,
    },
    {
        "name": "manager",
        "display_name": "Manager",
        "description": "Manages cameras, recordings, alerts, and reads notifications.",
        "permissions": [
            "cameras:view_live",
            "cameras:manage",
            "recordings:view",
            "recordings:export",
            "recordings:delete",
            "alerts:view",
            "alerts:acknowledge",
            "alerts:manage",
            "notifications:read",
        ],
        "is_system_role": True,
    },
    {
        "name": "operator",
        "display_name": "Operator",
        "description": "Views live cameras, recordings, and manages alerts.",
        "permissions": [
            "cameras:view_live",
            "recordings:view",
            "alerts:view",
            "alerts:acknowledge",
        ],
        "is_system_role": True,
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to live camera feeds.",
        "permissions": [
            "cameras:view_live",
        ],
        "is_system_role": True,
    },
    {
        "name": "api_client",
        "display_name": "API Client",
        "description": "Programmatic access for external integrations.",
        "permissions": [
            "cameras:view_live",
            "recordings:view",
            "alerts:view",
        ],
        "is_system_role": True,
    },
]


def seed(db) -> None:
    # --- Roles ---
    role_map: dict[str, Role] = {}
    for role_def in ROLES:
        existing = db.execute(
            select(Role).where(Role.name == role_def["name"])
        ).scalar_one_or_none()

        if existing is None:
            role = Role(
                name=role_def["name"],
                display_name=role_def["display_name"],
                description=role_def["description"],
                permissions=role_def["permissions"],
                is_system_role=role_def["is_system_role"],
            )
            db.add(role)
            db.flush()
            print(f"  Created role: {role_def['name']}")
            role_map[role_def["name"]] = role
        else:
            print(f"  Role already exists: {role_def['name']}")
            role_map[role_def["name"]] = existing

    # --- Initial superadmin user (only when no users exist) ---
    user_count = db.execute(select(User)).first()
    if user_count is not None:
        print("  Users already exist — skipping initial superadmin creation.")
        return

    superadmin_role = role_map["superadmin"]
    raw_password = secrets.token_urlsafe(12)
    ph = PasswordHasher()
    hashed = ph.hash(raw_password)

    admin_user = User(
        email="admin@nvr.internal",
        full_name="System Administrator",
        hashed_password=hashed,
        role_id=superadmin_role.id,
        is_active=True,
        must_change_password=True,
    )
    db.add(admin_user)
    db.flush()

    # Print ONLY to stdout — never to any log sink
    print("\n" + "=" * 60)
    print("  Initial superadmin user created.")
    print(f"  Email   : admin@nvr.internal")
    print(f"  Password: {raw_password}")
    print("  IMPORTANT: change this password immediately after first login.")
    print("=" * 60 + "\n")


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    print("Seeding roles and initial user…")
    db = Session()
    try:
        seed(db)
        db.commit()
        print("Done.")
    except Exception as exc:
        db.rollback()
        print(f"Error during seeding: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
