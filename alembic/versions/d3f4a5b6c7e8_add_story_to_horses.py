"""add story to horses

Revision ID: d3f4a5b6c7e8
Revises: b2e3f4a5c6d7
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f4a5b6c7e8'
down_revision: Union[str, Sequence[str], None] = 'b2e3f4a5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('horses', sa.Column('story', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('horses', 'story')
