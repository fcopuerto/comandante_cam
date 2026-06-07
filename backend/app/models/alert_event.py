from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import Severity
from app.database import Base


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_camera_triggered", "camera_id", "triggered_at"),
        Index(
            "ix_alert_events_unacknowledged",
            "acknowledged",
            "severity",
            postgresql_where=text("acknowledged = FALSE"),
        ),
        Index(
            "ix_alert_events_triggered_at_brin",
            "triggered_at",
            postgresql_using="brin",
        ),
    )

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    camera_id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("cameras.id", name="fk_alert_events_camera_id_cameras"),
        nullable=False,
    )
    alert_rule_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("alert_rules.id", name="fk_alert_events_alert_rule_id_alert_rules"),
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detection_type: Mapped[str | None] = mapped_column(String(50))
    zone_name: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity_enum", create_type=False), nullable=False
    )
    rule_triggered: Mapped[str | None] = mapped_column(String(100))
    bbox: Mapped[dict | None] = mapped_column(JSON)
    track_id: Mapped[int | None] = mapped_column(Integer)
    frame_path: Mapped[str | None] = mapped_column(Text)
    clip_path: Mapped[str | None] = mapped_column(Text)
    clip_checksum: Mapped[str | None] = mapped_column(String(64))
    is_false_positive: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_on_legal_hold: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    acknowledged: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    acknowledged_by: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_alert_events_acknowledged_by_users"),
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    camera: Mapped["Camera"] = relationship("Camera")  # type: ignore[name-defined]
    alert_rule: Mapped["AlertRule | None"] = relationship("AlertRule")  # type: ignore[name-defined]
    acknowledger: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[acknowledged_by]
    )
