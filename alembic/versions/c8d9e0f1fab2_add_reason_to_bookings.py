"""add reason to bookings

Revision ID: c8d9e0f1fab2
Revises: b7c8d9e0fab1
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d9e0f1fab2'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0fab1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('bookings', 'reason')
