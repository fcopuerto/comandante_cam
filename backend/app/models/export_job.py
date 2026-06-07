from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ExportStatus
from app.database import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    camera_ids: Mapped[list[str]] = mapped_column(
        ARRAY(pgUUID(as_uuid=False)), nullable=False
    )
    from_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, name="export_status_enum"),
        server_default=text("'queued'"),
        nullable=False,
    )
    progress_pct: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    password_protected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    watermark: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    watermark_text: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_export_jobs_requested_by_users"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined]
