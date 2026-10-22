"""
app/models/knowledge_base.py — 知识库 ORM 模型

依据：DB §2.24-2.27 / 切片 13-infrastructure/knowledge_base.md §2
表：knowledge_category, knowledge_entry, rule_definition, training_template
注意：training_advice 和 admin 模块通过 import 引用这些模型
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class KnowledgeCategory(Base):
    __tablename__ = "knowledge_category"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    code = Column(String(32), nullable=False, unique=True)
    content = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    entries = relationship(
        "KnowledgeEntry", back_populates="category", cascade="all, delete-orphan"
    )


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entry"
    __table_args__ = (
        Index("idx_knowledge_entry_content_gin", "content", postgresql_using="gin"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category_id = Column(
        BigInteger, ForeignKey("knowledge_category.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(128), nullable=False)
    content = Column(JSONB, nullable=False)
    entry_type = Column(String(32), nullable=False)  # action/problem/method/style/template
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    category = relationship("KnowledgeCategory", back_populates="entries")


class RuleDefinition(Base):
    __tablename__ = "rule_definition"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(String(64), nullable=False, unique=True)
    rule_name = Column(String(128), nullable=False)
    rule_type = Column(String(32), nullable=False)  # single/trend_persistent/trend_improving/stagnant/plan_effectiveness
    condition = Column(JSONB, nullable=False)
    diagnosis = Column(JSONB, nullable=False)
    training_methods = Column(JSONB, nullable=True)
    training_plan_template = Column(String(64), nullable=True)
    adjustment_action = Column(String(32), nullable=True)  # maintain/adjust/escalate/new_goal
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TrainingTemplate(Base):
    __tablename__ = "training_template"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    difficulty = Column(String(16), nullable=False, default="intermediate")
    description = Column(Text, nullable=True)
    problem_id = Column(String(64), nullable=True)
    template_data = Column(JSONB, nullable=False)
    template_config = Column(JSONB, nullable=False, default=dict)
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
