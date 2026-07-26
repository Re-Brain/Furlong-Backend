"""add position to horse_images

Revision ID: b2e3f4a5c6d7
Revises: aaa627f1b5e8
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2e3f4a5c6d7'
down_revision: Union[str, Sequence[str], None] = 'aaa627f1b5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('horse_images', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))

    op.execute("""
        UPDATE horse_images hi
        SET position = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY horse_id ORDER BY id) - 1 AS rn
            FROM horse_images
        ) sub
        WHERE hi.id = sub.id
    """)


def downgrade() -> None:
    op.drop_column('horse_images', 'position')
