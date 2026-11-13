"""R-FE-R2 Batch G: add match.opponent_playing_style

Revision ID: c7d8e9f0a1b2
Revises: b8c9d0e1f2a3
Create Date: 2026-11-13

FE-P2-14（v1.0 L487 对手打法四选项）：match 表补 opponent_playing_style
VARCHAR(20) NULL（fast_attack/loop_drive/chop/all_round）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "match",
        sa.Column("opponent_playing_style", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match", "opponent_playing_style")
