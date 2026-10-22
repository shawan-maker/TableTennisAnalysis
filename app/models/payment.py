"""
app/models/payment.py — 订单 + 支付记录 + 退款记录

依据：DB §2.18 order / §2.19 payment_record / §2.19b refund_record
      切片 11-payment/backend.md §3
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Order(Base):
    """订单"""

    __tablename__ = "order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"),
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subscription.id", ondelete="SET NULL"), nullable=True,
    )
    order_no: Mapped[str] = mapped_column(String(64), unique=True, comment="订单号")
    product_type: Mapped[str] = mapped_column(
        String(32), comment="membership/analysis_pack/equipment/tournament",
    )
    product_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, comment="金额(分)")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="pending/paid/refunded/cancelled",
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    subscription: Mapped["Subscription | None"] = relationship(back_populates="orders")
    payments: Mapped[list["PaymentRecord"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_order_user_created", "user_id", "created_at"),
        Index("idx_order_status", "status"),
    )


class PaymentRecord(Base):
    """支付记录"""

    __tablename__ = "payment_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order.id", ondelete="CASCADE"),
    )
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, comment="微信支付交易号")
    payment_method: Mapped[str] = mapped_column(
        String(20), comment="wechat_jsapi/wechat_app",
    )
    amount_cents: Mapped[int] = mapped_column(Integer, comment="支付金额(分)")
    callback_raw: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="验签后的回调明文",
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    order: Mapped["Order"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("idx_payment_order", "order_id"),
    )


class RefundRecord(Base):
    """退款记录"""

    __tablename__ = "refund_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order.id", ondelete="CASCADE"),
    )
    refund_no: Mapped[str] = mapped_column(String(64), unique=True)
    refund_amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reversal_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="退款类型：full/full_reversal/partial",
    )
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    callback_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_refund_order", "order_id"),
    )
