"""
app/models/membership.py — 会员等级配置 + 用户订阅记录

依据：DB §2.17 subscription / §2.31 membership_tier_config
      切片 10-membership/backend.md §3
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MembershipTierConfig(Base):
    """会员等级配置（预置数据，运营可修改）"""

    __tablename__ = "membership_tier_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tier: Mapped[str] = mapped_column(
        String(20), unique=True, comment="等级标识：free/member/pro/coach",
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False, comment="等级名称")
    price_monthly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="月价（分）")
    price_quarterly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="季价（分）")
    price_yearly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年价（分）")
    benefits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, comment="权益列表")
    quota_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, comment="额度配置")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Subscription(Base):
    """用户订阅记录"""

    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False, comment="会员等级")
    status: Mapped[str] = mapped_column(
        String(20), default="active",
        comment="状态：active/expiring_soon/expired/grace_period/cancelled/closed",
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="支付方式: manual/auto_deduct",
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="取消时间（退款撤销时设置）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("idx_sub_user_status", "user_id", "status"),
        Index("idx_sub_status_expire", "status", "expire_at"),
    )


# 避免循环导入
from app.models.payment import Order  # noqa: E402, F401
