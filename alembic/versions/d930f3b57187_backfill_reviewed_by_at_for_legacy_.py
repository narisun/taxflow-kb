"""backfill reviewed_by_at for legacy approved docs

Revision ID: d930f3b57187
Revises: 7ab5fa3d8cd6
Create Date: 2026-04-16 20:17:25.435476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd930f3b57187'
down_revision: Union[str, Sequence[str], None] = '7ab5fa3d8cd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill review audit for documents approved before the audit
    columns existed.

    For any row with ``status='approved'`` but no ``reviewed_at``:
      - Use ``updated_at`` as the best available proxy for the review time
        (the prior approve endpoint mutated the row, so updated_at is when
        the status flipped to ``approved``).
      - Use ``created_by`` as the proxy for the reviewer (we have no record
        of who actually clicked Approve historically — this is documented
        as best-effort in the column comment via the migration history).

    Newly-approved rows continue to be stamped accurately by the approve
    endpoint going forward.
    """
    op.execute(
        sa.text(
            """
            UPDATE documents
               SET reviewed_at = updated_at,
                   reviewed_by = created_by
             WHERE status = 'approved'
               AND reviewed_at IS NULL
            """
        )
    )


def downgrade() -> None:
    """Wipe the backfilled values so a re-up is idempotent. We can't tell
    backfilled vs genuine rows apart, so this clears all and the next
    upgrade re-runs the heuristic."""
    op.execute(
        sa.text(
            """
            UPDATE documents
               SET reviewed_at = NULL,
                   reviewed_by = NULL
             WHERE status = 'approved'
            """
        )
    )
