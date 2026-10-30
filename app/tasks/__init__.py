"""Celery tasks package — autodiscover 注册所有任务模块"""

# 导入所有任务模块以便 Celery autodiscover 发现
from app.tasks import (
    ai_inference_health,
    audit,
    dashboard,
    export,
    file_management,
    gamification,
    membership,
    notification,
    progress,
    scoring,
    training,
    user,
)

__all__ = [
    "ai_inference_health",
    "audit",
    "dashboard",
    "export",
    "file_management",
    "gamification",
    "membership",
    "notification",
    "progress",
    "scoring",
    "training",
    "user",
]
