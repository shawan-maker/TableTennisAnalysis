"""
app/models/user.py — User + RatingHistory ORM Models

依据：DB §2.1 user 表 / §2.3 rating_history 表
      切片 01-auth/backend.md §3 + 02-user/backend.md §3
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


class User(Base):
    """
    用户表 — auth 模块定义基础字段，user 模块扩展档案字段。
    DB 设计 §2.1 / v1.6: user_profile 已合并入 user 表。
    """

    __tablename__ = "user"

    # --- 基础字段（auth 模块） ---
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/pending_deletion/deleted/banned

    # --- 注销字段（PIPL 合规） ---
    scheduled_deletion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- 档案字段（user 模块扩展，原 user_profile 表合并） ---
    kqs_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kqs_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    playing_style: Mapped[str | None] = mapped_column(String(32), nullable=True)
    equipment_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    self_assessed_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile_completeness: Mapped[int] = mapped_column(Integer, default=0)

    # --- 时间戳 ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- 关系 ---
    rating_history: Mapped[list["RatingHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    consent_logs: Mapped[list["ConsentLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    export_tasks: Mapped[list["ExportTask"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 部分唯一索引：openid 非空时唯一
        Index("idx_user_openid", "openid", postgresql_where="openid IS NOT NULL"),
        # 部分唯一索引：phone 非空时唯一
        Index("idx_user_phone", "phone", postgresql_where="phone IS NOT NULL"),
        Index("idx_user_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, nickname={self.nickname!r}, status={self.status!r})>"


class RatingHistory(Base):
    """开球网积分历史记录 — DB §2.3"""

    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/kqs_api/tournament
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- 关系 ---
    user: Mapped["User"] = relationship(back_populates="rating_history")

    __table_args__ = (
        Index("idx_rating_user_recorded", "user_id", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<RatingHistory(id={self.id}, user_id={self.user_id}, rating={self.rating})>"


class ConsentLog(Base):
    """用户同意记录 — PIPL 合规审计 — DB §2.34"""

    __tablename__ = "consent_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)  # privacy_policy/data_processing
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # --- 关系 ---
    user: Mapped["User"] = relationship(back_populates="consent_logs")

    __table_args__ = (
        Index("idx_consent_user_type", "user_id", "consent_type"),
        Index("idx_consent_user_at", "user_id", "consent_at"),
    )

    def __repr__(self) -> str:
        return f"<ConsentLog(id={self.id}, user_id={self.user_id}, type={self.consent_type!r})>"


class ExportTask(Base):
    """个人数据导出任务 — PIPL 数据可携带权。DB §2.33"""

    __tablename__ = "export_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/completed/failed
    download_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- 关系 ---
    user: Mapped["User"] = relationship(back_populates="export_tasks")

    __table_args__ = (
        Index("idx_export_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ExportTask(id={self.id}, task_id={self.task_id!r}, status={self.status!r})>"
