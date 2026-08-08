"""add draft status default to horses

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New horses start as "draft" (still being assembled) rather than
    # "pending" (submitted, frozen). Existing rows are untouched — they were
    # already backfilled to "approved" when the status column was added.
    op.alter_column('horses', 'status', server_default='draft')


def downgrade() -> None:
    op.alter_column('horses', 'status', server_default='pending')
