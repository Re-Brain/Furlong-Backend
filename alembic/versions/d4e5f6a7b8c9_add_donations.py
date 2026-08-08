"""add donations

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1fab2
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1fab2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'donations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('farm_id', sa.Integer(), nullable=False),
        sa.Column('visitor_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('application_fee_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False, server_default='thb'),
        sa.Column('stripe_checkout_session_id', sa.String(), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['visitor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_checkout_session_id'),
    )
    op.create_index(op.f('ix_donations_id'), 'donations', ['id'], unique=False)
    op.create_index(op.f('ix_donations_stripe_checkout_session_id'), 'donations', ['stripe_checkout_session_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_donations_stripe_checkout_session_id'), table_name='donations')
    op.drop_index(op.f('ix_donations_id'), table_name='donations')
    op.drop_table('donations')
