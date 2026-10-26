"""R4-Pay-1: AuditLog.admin_id nullable=True + FK ondelete=SET NULL

Revision ID: b8c9d0e1f2a3
Revises: ('a1b2c3d4e5f6', 'a3b7c9d2e5f1')
Create Date: 2026-10-26 10:00:00+00:00

背景（R4-Pay-1）：payment_service 创建 AuditLog 时只设置 user_id（用户侧
支付/回调操作），从不设置 admin_id。原模型 admin_id 为 nullable=False，
导致非管理员审计日志插入触发 NOT NULL 约束违例。改为 nullable=True，
FK ondelete 由 RESTRICT 改为 SET NULL（管理员被删后审计日志保留，
admin_id 置空）。

注：迁移 7a614375bcf4 已将 admin_id 列添加为 nullable=True + FK SET NULL，
本迁移对齐模型与数据库约束，确保在所有环境下一致（幂等）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
# 合并两个 head（a1b2c3d4e5f6 partition / a3b7c9d2e5f1 add_notes）
down_revision: Union[str, None] = ("a1b2c3d4e5f6", "a3b7c9d2e5f1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. admin_id 改为 nullable=True（幂等：若已 nullable 则 no-op）
    op.alter_column(
        "audit_log", "admin_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        comment="操作管理员 ID（非管理员操作如支付时为空，user_id 有值）",
        existing_comment="操作管理员 ID",
    )
    # 2. FK ondelete 由 RESTRICT 改为 SET NULL
    #    约束名遵循 PostgreSQL 默认命名 {table}_{column}_fkey
    op.drop_constraint("audit_log_admin_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_admin_id_fkey",
        "audit_log", "admin_user",
        ["admin_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("audit_log_admin_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_admin_id_fkey",
        "audit_log", "admin_user",
        ["admin_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "audit_log", "admin_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        comment="操作管理员 ID",
        existing_comment="操作管理员 ID（非管理员操作如支付时为空，user_id 有值）",
    )
