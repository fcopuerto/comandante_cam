"""add osd fields to camera

Revision ID: a0b1c2d3e4f5
Revises: f1a2b3c4d5e6
Create Date: 2026-06-17 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('osd_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('cameras', sa.Column('osd_clock', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('cameras', sa.Column('osd_label', sa.Boolean(), server_default=sa.text('true'), nullable=False))


def downgrade() -> None:
    op.drop_column('cameras', 'osd_label')
    op.drop_column('cameras', 'osd_clock')
    op.drop_column('cameras', 'osd_enabled')
