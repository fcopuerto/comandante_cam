from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CameraPlacement(Base):
    __tablename__ = "camera_placements"
    __table_args__ = (
        UniqueConstraint("camera_id", name="uq_camera_placement_camera"),
    )

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    floor_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), ForeignKey("floors.id", ondelete="CASCADE"), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    x: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    y: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    rotation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    floor: Mapped["Floor"] = relationship("Floor", back_populates="placements")  # noqa: F821
    camera: Mapped["Camera"] = relationship("Camera")  # noqa: F821
