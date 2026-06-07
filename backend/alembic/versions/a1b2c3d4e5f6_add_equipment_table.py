"""add equipment table

Revision ID: a1b2c3d4e5f6
Revises: 4187467d1edf
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "4187467d1edf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_user", sa.String(64), nullable=False, server_default="pi"),
        sa.Column("ssh_password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("ssh_key_path", sa.String(256), nullable=True),
        sa.Column("device_type", sa.String(32), nullable=False, server_default="raspberry_pi"),
        sa.Column("location", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_equipment_device_type", "equipment", ["device_type"])
    op.create_index("ix_equipment_ip_address", "equipment", ["ip_address"])


def downgrade() -> None:
    op.drop_index("ix_equipment_ip_address", table_name="equipment")
    op.drop_index("ix_equipment_device_type", table_name="equipment")
    op.drop_table("equipment")
