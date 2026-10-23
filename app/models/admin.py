"""
app/models/admin.py — 管理后台 ORM Models

依据：DB §2.31 admin_user / §2.32 audit_log / §2.33 system_config
      切片 12-notification/admin backend.md
S5 创建 AuditLog，S6 补全 AdminUser + SystemConfig。
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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminUser(Base):
    """管理员用户表"""

    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="content_admin",
        comment="super_admin / content_admin / model_admin",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_admin_username", "username"),
    )


class SystemConfig(Base):
    """系统配置表"""

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column("config_key", String(128), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column("config_value", Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class AuditLog(Base):
    """审计日志 — 记录敏感操作（支付/退款/权限变更等）"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True,
        comment="操作管理员 ID",
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
        comment="操作者 ID（用户侧操作时记录）",
    )
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="操作类型",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="目标对象类型",
    )
    target_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="目标对象 ID",
    )
    changes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="变更详情 JSON",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="补充说明文本",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="操作者 IP 地址",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_audit_admin_created", "admin_id", "created_at"),
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_target", "target_type", "target_id"),
    )
