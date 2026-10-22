"""
app/models/gamification.py - 游戏化 ORM 模型

依据：DB 2.15-2.16, 3.1.4-3.1.6 / 切片 09-gamification/backend.md 2
表：user_points, checkin_record, badge_definition, user_badge, badge_progress
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class UserPoints(Base):
    __tablename__ = "user_points"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_points_user"),
        Index("idx_points_user_updated", "user_id", "updated_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    total_points = Column(Integer, nullable=False, default=0)
    monthly_points = Column(Integer, nullable=False, default=0)
    bonus_points = Column(Integer, nullable=False, default=0)
    current_streak = Column(Integer, nullable=False, default=0)
    last_checkin_date = Column(Date, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CheckInRecord(Base):
    __tablename__ = "checkin_record"
    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date"),
        Index("idx_checkin_user_date", "user_id", "checkin_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    checkin_date = Column(Date, nullable=False)
    checkin_type = Column(String(16), nullable=False, default="manual")
    points_earned = Column(Integer, nullable=False, default=2)
    bonus_points = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BadgeDefinition(Base):
    __tablename__ = "badge_definition"
    __table_args__ = (
        Index("idx_badge_definition_category", "category", "sort_order"),
        Index("idx_badge_definition_active", "is_active"),
    )

    id = Column(String(64), primary_key=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(16), nullable=False)
    category = Column(String(32), nullable=False, default="general")
    condition = Column(JSONB, nullable=False)
    points_reward = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class UserBadge(Base):
    __tablename__ = "user_badge"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
        Index("idx_user_badge_user", "user_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    badge_id = Column(
        String(64),
        ForeignKey("badge_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    earned_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BadgeProgress(Base):
    __tablename__ = "badge_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_badge_progress"),
        Index("idx_badge_progress_user", "user_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    badge_id = Column(
        String(64),
        ForeignKey("badge_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_value = Column(Integer, nullable=False, default=0)
    target_value = Column(Integer, nullable=False)
    progress_pct = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
