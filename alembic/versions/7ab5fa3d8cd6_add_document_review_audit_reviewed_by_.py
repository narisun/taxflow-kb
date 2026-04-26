"""add document review audit (reviewed_by, reviewed_at)

Revision ID: 7ab5fa3d8cd6
Revises: e41e2d4e91b6
Create Date: 2026-04-16 19:45:13.380241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ab5fa3d8cd6'
down_revision: Union[str, Sequence[str], None] = 'e41e2d4e91b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column('reviewed_by', sa.String(length=36), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        'fk_documents_reviewed_by_users',
        'documents', 'users',
        ['reviewed_by'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_documents_reviewed_by_users', 'documents', type_='foreignkey')
    op.drop_column('documents', 'reviewed_at')
    op.drop_column('documents', 'reviewed_by')
