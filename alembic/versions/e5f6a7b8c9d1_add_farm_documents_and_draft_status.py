"""add farm documents and draft status

Revision ID: e5f6a7b8c9d1
Revises: c3d4e5f6a7b8
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d1'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New farms start as "draft" (still being assembled) rather than
    # "pending" (submitted, frozen) — mirrors the horse status default.
    # Existing rows keep whatever status they already have.
    op.alter_column('farms', 'status', server_default='draft')

    op.create_table(
        'farm_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(), nullable=False),
        sa.Column('file_url', sa.String(), nullable=False),
        sa.Column('public_id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('farm_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_farm_documents_id'), 'farm_documents', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_farm_documents_id'), table_name='farm_documents')
    op.drop_table('farm_documents')
    op.alter_column('farms', 'status', server_default='pending')
