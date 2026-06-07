from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, SmallInteger, String, Time, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import RecordingMode
from app.database import Base


class RecordingSchedule(Base):
    __tablename__ = "recording_schedules"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", ondelete="CASCADE", name="fk_recording_schedules_camera_id_cameras"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(100))
    # 0=Mon … 6=Sun
    days_of_week: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{}'::smallint[]")
    )
    time_start: Mapped[time] = mapped_column(Time, nullable=False)
    time_end: Mapped[time] = mapped_column(Time, nullable=False)
    recording_mode: Mapped[RecordingMode | None] = mapped_column(
        Enum(RecordingMode, name="recording_mode_enum", create_type=False)
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    camera: Mapped["Camera"] = relationship("Camera")  # type: ignore[name-defined]
