"""
app/models/video_analysis.py — 视频分析模块 ORM 模型

依据：DB §2.4-2.8 / 切片 03-video_analysis/backend.md §3
表：file_record, video_task, pipeline_step, analysis_report, feedback_record
注意：share_record 在 match.py 中已定义（S2），S3 通过迁移补充 FK
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class FileRecord(Base):
    """文件记录 — OSS 直传追踪"""

    __tablename__ = "file_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    oss_key = Column(String(512), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=False)  # 1MB-500MB
    file_type = Column(String(20), nullable=False)  # mp4/mov
    status = Column(String(20), nullable=False, default="uploading")  # uploading/uploaded/abandoned/deleted
    oss_etag = Column(String(128), nullable=True)
    actual_size = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tasks = relationship("VideoTask", back_populates="file_record")

    __table_args__ = (
        CheckConstraint("file_size >= 1048576 AND file_size <= 524288000", name="ck_file_size_range"),
        Index("idx_file_record_user_created", "user_id", "created_at"),
        Index("idx_file_status_created", "status", "created_at"),
        Index("idx_file_record_type", "file_type"),
    )


class VideoTask(Base):
    """视频分析任务"""

    __tablename__ = "video_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(BigInteger, ForeignKey("file_record.id", ondelete="CASCADE"), nullable=False)
    oss_key = Column(String(512), nullable=False)
    duration_sec = Column(Integer, nullable=True)  # 5-600
    status = Column(String(20), nullable=False, default="queued")  # queued/processing/completed/failed/cancelled
    current_step = Column(Integer, nullable=False, default=0)  # 0-10
    task_uuid = Column(String(64), nullable=False, unique=True)
    total_steps = Column(Integer, nullable=False, default=10)
    step_name = Column(String(32), nullable=True)
    progress = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    estimated_remaining_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    file_record = relationship("FileRecord", back_populates="tasks")
    pipeline_steps = relationship("PipelineStep", backref="task", cascade="all, delete-orphan", order_by="PipelineStep.step_number")
    report = relationship("AnalysisReport", backref="task", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_video_task_user_created", "user_id", "created_at"),
        Index("idx_video_task_status_created", "status", "created_at"),
    )


class PipelineStep(Base):
    """流水线步骤记录"""

    __tablename__ = "pipeline_step"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("video_task.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)  # 1-10
    step_name = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed/skipped
    duration_ms = Column(Integer, nullable=True)
    step_result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pipeline_step_task_step", "task_id", "step_number"),
    )


class AnalysisReport(Base):
    """分析报告"""

    __tablename__ = "analysis_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("video_task.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    result_data = Column(JSONB, nullable=False)
    report_text = Column(JSONB, nullable=False)  # {summary, issues[], suggestions[]}
    annotated_video_url = Column(String(512), nullable=True)
    cover_image_url = Column(String(512), nullable=True)
    report_images = Column(JSONB, nullable=True)
    is_llm_generated = Column(Boolean, nullable=False, default=True)
    is_anonymized = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    feedbacks = relationship("FeedbackRecord", backref="report", cascade="all, delete-orphan")
    shares = relationship("ShareRecord", backref="report")

    __table_args__ = (
        Index("idx_report_user_created", "user_id", text("created_at DESC")),
        # 全文搜索 GIN 索引（to_tsvector）
        Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin"),
        # JSONB 查询 GIN 索引
        Index("idx_report_text_jsonb_gin", "report_text", postgresql_using="gin"),
    )


class FeedbackRecord(Base):
    """报告反馈 — 数据飞轮"""

    __tablename__ = "feedback_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    report_id = Column(BigInteger, ForeignKey("analysis_report.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending/archived/manual_review
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report"),
        Index("idx_feedback_status", "status"),
        Index("idx_feedback_correct_created", "is_correct", "created_at"),
    )
