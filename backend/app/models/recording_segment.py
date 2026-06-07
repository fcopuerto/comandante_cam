from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SegmentType
from app.database import Base


class RecordingSegment(Base):
    __tablename__ = "recording_segments"
    __table_args__ = (
        Index("ix_recording_segments_camera_time", "camera_id", "started_at", "ended_at"),
        Index("ix_recording_segments_camera_type", "camera_id", "segment_type"),
        Index(
            "ix_recording_segments_has_alert",
            "has_alert",
            postgresql_where=text("has_alert = TRUE"),
        ),
        Index(
            "ix_recording_segments_started_at_brin",
            "started_at",
            postgresql_using="brin",
        ),
    )

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", ondelete="CASCADE", name="fk_recording_segments_camera_id_cameras"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    segment_type: Mapped[SegmentType | None] = mapped_column(
        Enum(SegmentType, name="segment_type_enum")
    )
    has_motion: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    motion_score: Mapped[float | None] = mapped_column(Float)
    has_alert: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    alert_event_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("alert_events.id", name="fk_recording_segments_alert_event_id_alert_events"),
    )
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    is_corrupt: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_on_legal_hold: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(SmallInteger)
    height: Mapped[int | None] = mapped_column(SmallInteger)
    fps: Mapped[int | None] = mapped_column(SmallInteger)
    codec: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    camera: Mapped["Camera"] = relationship("Camera")  # type: ignore[name-defined]
    alert_event: Mapped["AlertEvent | None"] = relationship("AlertEvent")  # type: ignore[name-defined]
