"""
app/schemas/gamification.py - 游戏化 Schema
"""

from datetime import date, datetime
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


class BadgeLocked(BaseModel):
    badge_id: str
    name: str
    icon: str
    progress: int
    target: int


class BadgeListResponse(BaseModel):
    earned: list[BadgeEarned] = []
    locked: list[BadgeLocked] = []
