"""R2-P2-2 Batch H: point_transaction ledger table

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-16

R2-P2-2（批次H）：积分流水表 point_transaction——POINTS_SOURCE_MAP 设计常量
数据源（09-gamification/frontend.md §7 六来源此前零消费，后端无流水表/无历史
端点，纯前端方案不可行）。event_type 与 GamificationService._add_points
入参一致，GET /gamification/points-history 分页读取。add_column 级无损操作，
downgrade 直接 drop_table。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "point_transaction",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(32),
            nullable=False,
            comment="points source: analysis/match/record/checkin/streak_7/streak_30/training_session/share/feedback/badge",
        ),
        sa.Column("points", sa.Integer, nullable=False, comment="per-entry value"),
        sa.Column("ref_id", sa.BigInteger, nullable=True, comment="related business id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_point_txn_user_created", "point_transaction", ["user_id", "created_at"]
    )
    op.create_index(
        "idx_point_txn_user_event", "point_transaction", ["user_id", "event_type"]
    )


def downgrade() -> None:
    op.drop_index("idx_point_txn_user_event", table_name="point_transaction")
    op.drop_index("idx_point_txn_user_created", table_name="point_transaction")
    op.drop_table("point_transaction")
