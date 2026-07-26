"""add reminder_sent_at to bookings

Revision ID: b7c8d9e0fab1
Revises: a6c7d8e9fab0
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0fab1'
down_revision: Union[str, Sequence[str], None] = 'a6c7d8e9fab0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('bookings', 'reminder_sent_at')
