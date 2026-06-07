from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CameraPermission(Base):
    __tablename__ = "camera_permissions"

    user_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_camera_permissions_user_id_users"),
        primary_key=True,
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", ondelete="CASCADE", name="fk_camera_permissions_camera_id_cameras"),
        primary_key=True,
    )
    can_view_live: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    can_view_recordings: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    can_export_clips: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    can_configure: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    can_ptz: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    granted_by: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_camera_permissions_granted_by_users"),
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
    camera: Mapped["Camera"] = relationship("Camera")  # type: ignore[name-defined]
    granter: Mapped["User | None"] = relationship("User", foreign_keys=[granted_by])  # type: ignore[name-defined]
