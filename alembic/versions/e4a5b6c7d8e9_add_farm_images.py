"""add farm_images

Revision ID: e4a5b6c7d8e9
Revises: d3f4a5b6c7e8
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'd3f4a5b6c7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'farm_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('image_url', sa.String(), nullable=False),
        sa.Column('image_public_id', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('farm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_farm_images_id'), 'farm_images', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_farm_images_id'), table_name='farm_images')
    op.drop_table('farm_images')
