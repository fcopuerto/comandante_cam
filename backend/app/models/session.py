from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserSession(Base):
    """Stores refresh tokens. The session id IS the refresh token value."""

    __tablename__ = "sessions"

    # The UUID is used as the opaque refresh token sent to the client
    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id_users"),
        nullable=False,
    )
    device_name: Mapped[str | None] = mapped_column(String(200))
    device_fingerprint: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    is_revoked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(50))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
