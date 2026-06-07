from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, MACADDR
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CameraStatus, Codec, RecordingMode
from app.database import Base

_IP_CHECK = r"ip_address ~ '^[0-9a-fA-F.:\/]+$'"
_VPN_CHECK = r"vpn_host IS NULL OR vpn_host ~ '^[0-9a-fA-F.:\/]+$'"


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(_IP_CHECK, name="ip_address_format"),
        CheckConstraint(_VPN_CHECK, name="vpn_host_format"),
    )

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    rtsp_main_url: Mapped[str | None] = mapped_column(Text)
    rtsp_sub_url: Mapped[str | None] = mapped_column(Text)
    onvif_port: Mapped[int] = mapped_column(Integer, server_default=text("80"))
    username: Mapped[str | None] = mapped_column(String(100))
    # Fernet-encrypted camera password (BYTEA) — never returned in API responses
    password_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    onvif_profile_main: Mapped[str | None] = mapped_column(String(50))
    onvif_profile_sub: Mapped[str | None] = mapped_column(String(50))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    firmware_version: Mapped[str | None] = mapped_column(String(50))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    mac_address: Mapped[str | None] = mapped_column(MACADDR)
    is_vpn: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    vpn_host: Mapped[str | None] = mapped_column(String(45))
    group_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("camera_groups.id", name="fk_cameras_group_id_camera_groups"),
    )
    zone_location: Mapped[str | None] = mapped_column(String(200))
    building: Mapped[str | None] = mapped_column(String(100))
    floor: Mapped[str | None] = mapped_column(String(50))
    map_x: Mapped[float | None] = mapped_column(Float)
    map_y: Mapped[float | None] = mapped_column(Float)
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus, name="camera_status_enum"),
        server_default=text("'unknown'"),
    )
    recording_mode: Mapped[RecordingMode] = mapped_column(
        Enum(RecordingMode, name="recording_mode_enum"),
        server_default=text("'continuous'"),
    )
    resolution_main: Mapped[str | None] = mapped_column(String(20))
    resolution_sub: Mapped[str | None] = mapped_column(String(20))
    fps: Mapped[int] = mapped_column(SmallInteger, server_default=text("25"))
    bitrate_kbps: Mapped[int] = mapped_column(Integer, server_default=text("2000"))
    codec: Mapped[Codec] = mapped_column(
        Enum(Codec, name="codec_enum"),
        server_default=text("'h264'"),
    )
    retention_days: Mapped[int] = mapped_column(SmallInteger, server_default=text("30"))
    pre_event_seconds: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    post_event_seconds: Mapped[int] = mapped_column(SmallInteger, server_default=text("10"))
    ntp_synced: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    last_ntp_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_errors: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    detection_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    privacy_mask: Mapped[dict | None] = mapped_column(JSON)
    ptz_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ptz_presets: Mapped[dict | None] = mapped_column(JSON)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'::text[]")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Soft delete fields (SPEC.md §13)
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_cameras_created_by_users"),
    )

    group: Mapped["CameraGroup | None"] = relationship("CameraGroup")  # type: ignore[name-defined]
