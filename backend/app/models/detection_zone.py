from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Time, func, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DetectionZone(Base):
    __tablename__ = "detection_zones"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", ondelete="CASCADE", name="fk_detection_zones_camera_id_cameras"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # [[x, y], ...] normalised 0.0–1.0
    polygon: Mapped[dict] = mapped_column(JSON, nullable=False)
    restricted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    working_hours_start: Mapped[time | None] = mapped_column(Time)
    working_hours_end: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(50), server_default=text("'UTC'"))
    dwell_threshold_s: Mapped[int] = mapped_column(SmallInteger, server_default=text("30"))
    color: Mapped[str | None] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    camera: Mapped["Camera"] = relationship("Camera")  # type: ignore[name-defined]
