"""add email_verified to users

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True))
    # Grandfather in every existing account — nobody who's already using the
    # app should get locked out of login by this new requirement.
    op.execute("UPDATE users SET email_verified = true")
    op.alter_column('users', 'email_verified', nullable=False, server_default=sa.false())


def downgrade() -> None:
    op.drop_column('users', 'email_verified')
