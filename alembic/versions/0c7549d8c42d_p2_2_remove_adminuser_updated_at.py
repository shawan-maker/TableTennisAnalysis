"""P2-2: Remove AdminUser.updated_at

Revision ID: 0c7549d8c42d
Revises: 7a614375bcf4
Create Date: 2026-10-23 05:51:46.126117+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0c7549d8c42d'
down_revision: Union[str, None] = '7a614375bcf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('admin_user', 'updated_at')


def downgrade() -> None:
    op.add_column('admin_user', sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False))
