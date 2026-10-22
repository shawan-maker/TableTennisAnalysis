"""
app/models/progress.py - 进度分析 ORM 模型

依据：DB 2.21-2.22 / 切片 08-progress_analysis/backend.md 3
表：progress_snapshot, technique_trend
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class ProgressSnapshot(Base):
    __tablename__ = "progress_snapshot"
    __table_args__ = (
        Index("idx_ps_user_created", "user_id", "created_at"),
        Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    report_id = Column(
        BigInteger,
        ForeignKey("analysis_report.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    metrics_snapshot = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TechniqueTrend(Base):
    __tablename__ = "technique_trend"
    __table_args__ = (
        UniqueConstraint("user_id", "metric_name", name="uq_trend_user_metric"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    metric_name = Column(String(64), nullable=False)
    current_value = Column(Float, nullable=True)
    previous_value = Column(Float, nullable=True)
    change_rate = Column(Float, nullable=True)
    trend = Column(String(20), nullable=True)
    target_value = Column(Float, nullable=True)
    persistence_count = Column(Integer, nullable=False, default=0)
    time_series = Column(JSONB, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
