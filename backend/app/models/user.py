from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("roles.id", name="fk_users_role_id_roles"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_mfa_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Fernet-encrypted TOTP secret
    mfa_secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_backup_codes: Mapped[dict | None] = mapped_column(JSON)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(45))
    preferred_language: Mapped[str] = mapped_column(String(10), server_default=text("'en'"))
    preferred_timezone: Mapped[str] = mapped_column(String(50), server_default=text("'UTC'"))
    ui_preferences: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_users_created_by_users"),
    )
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped["Role | None"] = relationship("Role", foreign_keys=[role_id])  # type: ignore[name-defined]
