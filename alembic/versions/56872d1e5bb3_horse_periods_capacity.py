"""horse periods capacity

Converts horses.periods from a list of period keys (e.g. ["morning", "afternoon"])
to a per-period capacity map (e.g. {"morning": 1, "afternoon": 1, "evening": 0}).
No column shape change (still JSONB) — this only rewrites existing values. Rows
where periods IS NULL ("never configured") are left untouched; they keep meaning
"unset" and still resolve to a default capacity of 1 per period at read time.

Revision ID: 56872d1e5bb3
Revises: f6a7b8c9d1e2
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = '56872d1e5bb3'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Each period a horse's old list included gets a default capacity of 1;
    # every period it didn't include becomes 0.
    op.execute("""
        UPDATE horses
        SET periods = jsonb_build_object(
            'morning', CASE WHEN periods ? 'morning' THEN 1 ELSE 0 END,
            'afternoon', CASE WHEN periods ? 'afternoon' THEN 1 ELSE 0 END,
            'evening', CASE WHEN periods ? 'evening' THEN 1 ELSE 0 END
        )
        WHERE periods IS NOT NULL
    """)


def downgrade() -> None:
    # Reverse mapping: any period with capacity > 0 goes back into the list;
    # a horse left with no positive-capacity periods becomes an empty list
    # (not NULL — NULL specifically means "never configured").
    op.execute("""
        UPDATE horses
        SET periods = COALESCE(
            (SELECT jsonb_agg(key) FROM jsonb_each_text(periods) WHERE value::int > 0),
            '[]'::jsonb
        )
        WHERE periods IS NOT NULL
    """)
