"""Drop unused booking reminder_sent_at column

Revision ID: ba003ed2ebac
Revises: 9c1a2b3d4e5f
Create Date: 2026-09-05 23:26:41.560705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ba003ed2ebac'
down_revision: Union[str, Sequence[str], None] = '9c1a2b3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only reminder_sent_at is intentional here. Autogenerate also picked up
    # pre-existing horses.farm_id drift (nullable/FK ondelete) unrelated to
    # this change -- left out so this migration does only what its name says.
    op.drop_column('bookings', 'reminder_sent_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('bookings', sa.Column('reminder_sent_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
