"""
app/models/__init__.py — ORM Model 注册

所有 Model 在此导入，确保 Alembic 自动检测到表定义。
"""

from app.models.user import ConsentLog, RatingHistory, User
from app.models.match import (
    ManualScoreDetail,
    Match,
    MatchRecord,
    MatchStatistic,
    ScoreRecord,
    ShareRecord,
)
from app.models.notification import NotificationRecord

__all__ = [
    "User",
    "RatingHistory",
    "ConsentLog",
    "Match",
    "ScoreRecord",
    "MatchStatistic",
    "MatchRecord",
    "ManualScoreDetail",
    "ShareRecord",
    "NotificationRecord",
    "Base",
]
