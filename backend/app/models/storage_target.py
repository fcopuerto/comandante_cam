from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StorageTarget(Base):
    __tablename__ = "storage_targets"

    id: Mapped[str] = mapped_column(
        pgUUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(20))  # nfs, smb, local
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    export_path: Mapped[str] = mapped_column(String(500))
    mount_point: Mapped[str] = mapped_column(String(500))
    mount_options: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
