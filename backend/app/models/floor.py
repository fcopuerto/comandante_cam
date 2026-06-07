from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Floor(Base):
    __tablename__ = "floors"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    building_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0)
    plan_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    building: Mapped["Building"] = relationship("Building", back_populates="floors")  # noqa: F821
    placements: Mapped[list["CameraPlacement"]] = relationship(  # noqa: F821
        "CameraPlacement", back_populates="floor", cascade="all, delete-orphan"
    )
