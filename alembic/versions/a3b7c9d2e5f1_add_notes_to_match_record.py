"""add_notes_to_match_record

Revision ID: a3b7c9d2e5f1
Revises: 518ebf2e88b2
Create Date: 2026-10-23 08:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b7c9d2e5f1'
down_revision: Union[str, None] = '518ebf2e88b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('match_record', sa.Column('notes', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('match_record', 'notes')
