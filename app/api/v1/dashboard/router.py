"""
app/api/v1/dashboard/router.py — 数据看板 API 路由

依据：切片 06-data_dashboard/backend.md §6
5 个端点：overview / win-rate-trend / technique-stats / landing-heatmap / match-records
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["数据看板"])


@limiter.limit("100/minute")
@router.get("/overview", summary="概览卡片")
async def get_overview(
    request: Request,
    user: User = Depends(get_current_user),
):
    """胜率/分析次数/训练频次/连续天数/趋势。缓存 5min。"""
    data = await DashboardService.get_overview(user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/win-rate-trend", summary="战绩趋势")
async def get_win_rate_trend(
    request: Request,
    period: str = Query(default="month", pattern="^(month|quarter|year)$"),
    user: User = Depends(get_current_user),
):
    """战绩趋势折线图数据。缓存 1h。"""
    data = await DashboardService.get_win_rate_trend(user.id, period=period)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/technique-stats", summary="技术统计")
async def get_technique_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """技术统计环形图数据。缓存 1h。"""
    data = await DashboardService.get_technique_stats(user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/landing-heatmap", summary="累计落点热图")
async def get_landing_heatmap(
    request: Request,
    user: User = Depends(get_current_user),
):
    """累计落点热图（跨多次报告聚合九宫格）。缓存 1h。"""
    data = await DashboardService.get_landing_heatmap(user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/match-records", summary="比赛记录列表")
async def get_match_records(
    request: Request,
    result: str = Query(default="all", pattern="^(win|lose|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """比赛记录列表（分页，实时查询不缓存）。"""
    data = await DashboardService.get_match_records(
        user.id, result_filter=result, page=page, page_size=page_size
    )
    return success(data=data)
