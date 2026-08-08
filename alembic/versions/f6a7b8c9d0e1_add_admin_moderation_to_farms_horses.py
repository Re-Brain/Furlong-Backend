"""add admin moderation to farms and horses

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('farms', sa.Column('rejection_reason', sa.Text(), nullable=True))

    op.add_column('horses', sa.Column('status', sa.String(), nullable=True))
    # Existing horses were all effectively live before this gate existed —
    # backfill them to "approved" so nothing disappears from public listings.
    op.execute("UPDATE horses SET status = 'approved'")
    op.alter_column('horses', 'status', nullable=False, server_default='pending')
    op.add_column('horses', sa.Column('rejection_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('horses', 'rejection_reason')
    op.drop_column('horses', 'status')
    op.drop_column('farms', 'rejection_reason')
