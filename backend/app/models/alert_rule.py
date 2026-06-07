from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import Severity
from app.database import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # NULL = applies to all cameras
    camera_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", name="fk_alert_rules_camera_id_cameras"),
    )
    detection_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'::text[]")
    )
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity_enum"), nullable=False
    )
    # {days:[0..6], time_start, time_end} or NULL (always active)
    schedule: Mapped[dict | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Array of notification_channel UUIDs — no FK constraint because PG arrays don't support it
    notification_channels: Mapped[list[str]] = mapped_column(
        ARRAY(pgUUID(as_uuid=False)), server_default=text("'{}'::uuid[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    camera: Mapped["Camera | None"] = relationship("Camera")  # type: ignore[name-defined]
