"""
app/models/admin.py — 管理后台 ORM Models

依据：DB §2.32 audit_log 表
      切片 12-notification/admin backend.md（S6 扩展）
S5 阶段仅创建 AuditLog，AdminUser 在 S6 补全。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """审计日志 — 记录敏感操作（支付/退款/权限变更等）"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
        comment="操作者 ID（系统操作可为空）",
    )
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="操作类型（如 payment_order_created/refund/subscription_created_or_renewed）",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="目标对象类型（order/subscription/user 等）",
    )
    target_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="目标对象 ID",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="操作详情 JSON 字符串",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="操作者 IP 地址",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_target", "target_type", "target_id"),
    )
