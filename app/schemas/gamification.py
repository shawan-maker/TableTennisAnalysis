"""
app/schemas/gamification.py - 游戏化 Schema
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class PointsResponse(BaseModel):
    total_points: int = 0
    monthly_points: int = 0
    current_streak: int = 0
    streak_icon: str = ""


class CheckInDay(BaseModel):
    date: date
    checked_in: bool = False
    type: Optional[str] = None


class CheckInCalendarResponse(BaseModel):
    year: int
    month: int
    days: list[CheckInDay] = []
    monthly_checkin_count: int = 0
    streak_days: int = 0


class CheckInResponse(BaseModel):
    points_earned: int
    current_streak: int
    bonus: Optional[int] = None


class BadgeEarned(BaseModel):
    badge_id: str
    name: str
    icon: str
    earned_at: str
    # R2-P2-1（批次H）：分类透出——数据层 BadgeDefinition.category 早已就绪
    # （idx_badge_definition_category + 种子），schema 此前不暴露导致前端
    # BADGE_CATEGORY_MAP 常量零消费（孤儿）、4 个 i18n 分类键无渲染路径
    category: Optional[str] = None


class BadgeLocked(BaseModel):
    badge_id: str
    name: str
    icon: str
    progress: int
    target: int
    # R2-P2-1（批次H）：同 BadgeEarned
    category: Optional[str] = None


class BadgeListResponse(BaseModel):
    earned: list[BadgeEarned] = []
    locked: list[BadgeLocked] = []


class PointTransactionBrief(BaseModel):
    """积分流水条目（R2-P2-2 批次H）

    event_type 与 POINTS_SOURCE_MAP 六来源键一致（analysis/match/record/
    checkin/streak_7/streak_30），另含 training_session/share/feedback/badge。
    """

    id: int
    event_type: str
    points: int
    ref_id: Optional[int] = None
    created_at: Optional[str] = None


class PointsHistoryResponse(BaseModel):
    """积分历史分页响应（GET /gamification/points-history，R2-P2-2 批次H）"""

    total: int
    page: int
    page_size: int
    items: list[PointTransactionBrief] = []
