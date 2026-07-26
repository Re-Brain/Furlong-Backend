"""add visit availability and horse periods

Revision ID: f5b6c7d8e9fa
Revises: e4a5b6c7d8e9
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f5b6c7d8e9fa'
down_revision: Union[str, Sequence[str], None] = 'e4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('farms', sa.Column('availability', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('horses', sa.Column('periods', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('horses', 'periods')
    op.drop_column('farms', 'availability')
