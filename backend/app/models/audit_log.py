from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """
    Append-only. No UPDATE or DELETE permitted on this table.
    Enforced at DB level via PostgreSQL RLS (see Session 15 migration).
    """

    __tablename__ = "audit_log"

    # BIGSERIAL for high-volume write throughput — not UUID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # NULL for system-generated events
    user_id: Mapped[str | None] = mapped_column(
        pgUUID(as_uuid=False),
        ForeignKey("users.id", name="fk_audit_log_user_id_users", ondelete="SET NULL"),
    )
    # Denormalised snapshot of email at log time — preserved even after user anonymisation
    user_email: Mapped[str | None] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(36))
    severity: Mapped[str] = mapped_column(String(20), server_default=text("'info'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
