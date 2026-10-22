"""
app/models/training.py - 训练方案 ORM 模型

依据：DB 2.28, 2.23 / 切片 07-training_advice/backend.md 3
表：training_plan, plan_adjustment
注意：RuleDefinition 和 TrainingTemplate 定义在 knowledge_base.py，此处 import 引用
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class TrainingPlan(Base):
    __tablename__ = "training_plan"
    __table_args__ = (
        Index("idx_tplan_user_status", "user_id", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    template_id = Column(
        BigInteger,
        ForeignKey("training_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(20), nullable=False, default="active")  # active/completed/abandoned
    version = Column(Integer, nullable=False, default=1)
    plan_data = Column(JSONB, nullable=False)
    goal_metrics = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PlanAdjustment(Base):
    __tablename__ = "plan_adjustment"
    __table_args__ = (
        Index("idx_padj_plan", "training_plan_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    training_plan_id = Column(
        BigInteger,
        ForeignKey("training_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger_report_id = Column(
        BigInteger,
        ForeignKey("analysis_report.id", ondelete="SET NULL"),
        nullable=True,
    )
    old_plan_snapshot = Column(JSONB, nullable=True)
    new_plan_snapshot = Column(JSONB, nullable=False)
    adjustment_reason = Column(Text, nullable=False)
    adjustment_action = Column(String(32), nullable=False)  # maintain/adjust/escalate/new_goal
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
