"""
app/api/v1/match_data/router.py — 比赛数据模块 API 路由

依据：API §7 match-data 端点契约 / 切片 05-match_data/backend.md §4
规范：路由只调用 Service，禁止在路由中写业务逻辑
S2 实现：4 个 match-data 端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.schemas.match_data import MatchRecordCreateRequest, MatchRecordUpdate
from app.services.match_data_service import MatchDataService

router = APIRouter(prefix="/match-data", tags=["比赛数据"])


@router.post("/records", summary="创建比赛记录")
@limiter.limit(RateLimits.DEFAULT)
async def create_record(
    body: MatchRecordCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建比赛记录（快速/详细录入）"""
    data = await MatchDataService.create_record(user.id, body)
    return success(data=data, message="比赛记录已创建")


@router.get("/records", summary="比赛记录列表")
@limiter.limit(RateLimits.DEFAULT)
async def list_records(
    request: Request,
    result: Optional[str] = Query(default="all", pattern="^(win|lose|all)$", description="结果过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """比赛记录列表（分页）"""
    data = await MatchDataService.list_records(user.id, result, page, page_size)
    return success(data=data)


@router.get("/records/{record_id}", summary="比赛记录详情")
@limiter.limit(RateLimits.DEFAULT)
async def get_record(
    request: Request,
    record_id: int,
    user: User = Depends(get_current_user),
):
    """比赛记录详情（含得分明细）"""
    data = await MatchDataService.get_detail(user.id, record_id)
    return success(data=data)


@router.patch("/records/{record_id}", summary="编辑比赛记录")
@limiter.limit(RateLimits.DEFAULT)
async def update_record(
    body: MatchRecordUpdate,
    request: Request,
    record_id: int,
    user: User = Depends(get_current_user),
):
    """编辑比赛记录（PATCH 语义，仅限未关联记分牌的记录）"""
    data = await MatchDataService.update_record(user.id, record_id, body)
    return success(data=data, message="比赛记录已更新")
