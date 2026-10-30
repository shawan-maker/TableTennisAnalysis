"""
app/api/v1/progress/router.py - 进度分析 API 路由

依据：API 9 / 切片 08-progress_analysis/backend.md 6
6 个端点：snapshots / technique-trends / technique-trends/{metric} / comparison / summary / problem-changes
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.progress_service import ProgressService
from typing import Optional

router = APIRouter(prefix="/progress", tags=["进度分析"])


@router.get("/snapshots", summary="快照列表")
@limiter.limit("100/minute")
async def list_snapshots(
    request: Request,
    period: str = Query(default="all", pattern="^(month|quarter|year|all)$"),
    # R4-Progress-11: 添加 status 过滤参数
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    data = await ProgressService.list_snapshots(user.id, period=period, status=status, page=page, page_size=page_size)
    return success(data=data)


@router.get("/technique-trends", summary="技术趋势")
@limiter.limit("100/minute")
async def get_technique_trends(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_technique_trends(user.id)
    return success(data=data)


@router.get("/technique-trends/{metric}", summary="单项趋势详情")
@limiter.limit("100/minute")
async def get_technique_trend_detail(
    request: Request,
    metric: str,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_technique_trend_detail(user.id, metric)
    return success(data=data)


@router.get("/comparison", summary="报告对比")
@limiter.limit("100/minute")
async def get_comparison(
    request: Request,
    report_a: int = Query(ge=1),
    report_b: int = Query(ge=1),
    user: User = Depends(get_current_user),
):
    if report_a == report_b:
        raise AppException("两份报告不能相同", 422, code=42201)
    data = await ProgressService.get_comparison(user.id, report_a, report_b)
    if not data:
        raise AppException("报告不存在", 404, code=40412)
    return success(data=data)


@router.get("/summary", summary="综合摘要")
@limiter.limit("100/minute")
async def get_summary(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_summary(user.id)
    return success(data=data)


@router.get("/problem-changes", summary="问题变化")
@limiter.limit("100/minute")
async def get_problem_changes(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_problem_changes(user.id)
    return success(data=data)
