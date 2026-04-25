"""multi_year_draft_source_tracking

Revision ID: 308d5fead82c
Revises: 8131925e09ad
Create Date: 2026-04-25 16:45:03.969524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '308d5fead82c'
down_revision: Union[str, Sequence[str], None] = '8131925e09ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tax_return_drafts', sa.Column('source_type', sa.String(length=20), server_default='computed', nullable=False))
    op.add_column('tax_return_drafts', sa.Column('source_document_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_draft_source_doc', 'tax_return_drafts', 'documents', ['source_document_id'], ['id'])
    # Replace single-client unique constraint with per-year constraint.
    # Try both possible constraint names (manually named vs auto-generated).
    try:
        op.drop_constraint('uq_draft_org_client', 'tax_return_drafts', type_='unique')
    except Exception:
        pass
    op.create_unique_constraint('uq_draft_org_client_year', 'tax_return_drafts', ['org_id', 'client_id', 'tax_year'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_draft_org_client_year', 'tax_return_drafts', type_='unique')
    op.drop_constraint('fk_draft_source_doc', 'tax_return_drafts', type_='foreignkey')
    op.drop_column('tax_return_drafts', 'source_document_id')
    op.drop_column('tax_return_drafts', 'source_type')
    op.create_unique_constraint('uq_draft_org_client', 'tax_return_drafts', ['org_id', 'client_id'])
