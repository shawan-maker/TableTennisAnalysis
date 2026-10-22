"""
app/api/v1/gamification/router.py - 游戏化 API 路由

依据：API 10 / 切片 09-gamification/backend.md 6
4 个端点：points / checkin-calendar / checkin / badges
"""

from datetime import date
from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.gamification_service import GamificationService, BadgeService

router = APIRouter(prefix="/gamification", tags=["游戏化/积分徽章"])


@limiter.limit("100/minute")
@router.get("/points", summary="积分查询")
async def get_points(
    request: Request,
    user: User = Depends(get_current_user),
):
    async with async_session_factory() as db:
        data = await GamificationService.get_points(db, user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/checkin-calendar", summary="打卡日历")
async def get_checkin_calendar(
    request: Request,
    year: int = Query(default=None, ge=2020, le=2100),
    month: int = Query(default=None, ge=1, le=12),
    user: User = Depends(get_current_user),
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    async with async_session_factory() as db:
        data = await GamificationService.get_checkin_calendar(db, user.id, y, m)
    return success(data=data)


@limiter.limit("1/day")
@router.post("/checkin", summary="每日打卡")
async def checkin(
    request: Request,
    user: User = Depends(get_current_user),
):
    async with async_session_factory() as db:
        data = await GamificationService.checkin(db, user.id)
        await db.commit()
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/badges", summary="徽章列表")
async def get_badges(
    request: Request,
    user: User = Depends(get_current_user),
):
    async with async_session_factory() as db:
        data = await BadgeService.get_badges(db, user.id)
    return success(data=data)
