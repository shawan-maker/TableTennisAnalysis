"""
app/models/notification.py — NotificationRecord ORM

依据：DB §2.20 notification_record
      切片 12-notification/backend.md §3
S2 仅建表，完整 NotificationService 在 S6 实现。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationRecord(Base):
    """
    通知记录 — DB §2.20
    S2 仅建表 + 基础 WS 推送，完整通知系统在 S6。
    分区策略：按月分区（开发阶段暂不分区，生产环境通过迁移脚本实现）。
    """

    __tablename__ = "notification_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # analysis_complete/payment_success/training_reminder/...
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {task_id, match_id, ...}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_notif_user_read_created", "user_id", "is_read", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<NotificationRecord(id={self.id}, user_id={self.user_id}, type={self.type!r})>"
