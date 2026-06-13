"""allow hostname in camera ip_address

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen column to fit FQDNs (max 253 chars)
    op.alter_column('cameras', 'ip_address', type_=sa.String(253), existing_nullable=False)

    # Drop old hex-only constraints and replace with hostname-aware ones
    op.drop_constraint('ck_cameras_ip_address_format', 'cameras', type_='check')
    op.drop_constraint('ck_cameras_vpn_host_format', 'cameras', type_='check')

    op.create_check_constraint(
        'ck_cameras_ip_address_format',
        'cameras',
        r"ip_address ~ '^[0-9a-zA-Z.\-:\[\]\/]+$'",
    )
    op.create_check_constraint(
        'ck_cameras_vpn_host_format',
        'cameras',
        r"vpn_host IS NULL OR vpn_host ~ '^[0-9a-zA-Z.\-:\[\]\/]+$'",
    )


def downgrade() -> None:
    op.drop_constraint('ck_cameras_ip_address_format', 'cameras', type_='check')
    op.drop_constraint('ck_cameras_vpn_host_format', 'cameras', type_='check')

    op.alter_column('cameras', 'ip_address', type_=sa.String(45), existing_nullable=False)

    op.create_check_constraint(
        'ck_cameras_ip_address_format',
        'cameras',
        r"ip_address ~ '^[0-9a-fA-F.:\/]+$'",
    )
    op.create_check_constraint(
        'ck_cameras_vpn_host_format',
        'cameras',
        r"vpn_host IS NULL OR vpn_host ~ '^[0-9a-fA-F.:\/]+$'",
    )
