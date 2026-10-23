"""
app/models/__init__.py — ORM Model 注册

所有 Model 在此导入，确保 Alembic 自动检测到表定义。
"""

from app.models.user import ConsentLog, ExportTask, RatingHistory, User
from app.models.match import (
    ManualScoreDetail,
    Match,
    MatchRecord,
    MatchStatistic,
    ScoreRecord,
    ShareRecord,
)
from app.models.notification import NotificationRecord
from app.models.video_analysis import (
    AnalysisReport,
    FeedbackRecord,
    FileRecord,
    PipelineStep,
    VideoTask,
)
from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.gamification import (
    BadgeDefinition,
    BadgeProgress,
    CheckInRecord,
    UserBadge,
    UserPoints,
)
from app.models.training import PlanAdjustment, TrainingPlan
from app.models.membership import MembershipTierConfig, Subscription
from app.models.payment import Order, PaymentRecord, RefundRecord
from app.models.admin import AdminUser, AuditLog, SystemConfig

__all__ = [
    "User",
    "RatingHistory",
    "ConsentLog",
    "ExportTask",
    "Match",
    "ScoreRecord",
    "MatchStatistic",
    "MatchRecord",
    "ManualScoreDetail",
    "ShareRecord",
    "NotificationRecord",
    "FileRecord",
    "VideoTask",
    "PipelineStep",
    "AnalysisReport",
    "FeedbackRecord",
    "KnowledgeCategory",
    "KnowledgeEntry",
    "RuleDefinition",
    "TrainingTemplate",
    "ProgressSnapshot",
    "TechniqueTrend",
    "BadgeDefinition",
    "BadgeProgress",
    "CheckInRecord",
    "UserBadge",
    "UserPoints",
    "TrainingPlan",
    "PlanAdjustment",
    "MembershipTierConfig",
    "Subscription",
    "Order",
    "PaymentRecord",
    "RefundRecord",
    "AuditLog",
    "AdminUser",
    "SystemConfig",
    "Base",
]
