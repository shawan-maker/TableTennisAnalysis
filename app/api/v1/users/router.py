"""
app/api/v1/users/router.py — 用户模块 API 路由

依据：API §3 user 端点契约 / 切片 02-user/backend.md
规范：路由只调用 Service，禁止在路由中写业务逻辑
S1 实现：GET /users/profile / PATCH /users/profile / GET /users/quota / PATCH /users/rating / GET /users/rating-history
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import RateLimits, limiter
from app.core.pagination import PaginationParams
from app.core.response import success
from app.models.user import User
from app.schemas.user import (
    AccountDeletionRequest,
    ProfileUpdateRequest,
    RatingUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["用户"])


@limiter.limit(RateLimits.DEFAULT)
@router.get("/profile", summary="获取个人档案")
async def get_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的个人档案"""
    data = await UserService.get_profile(user, db)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.patch("/profile", summary="更新个人档案")
async def update_profile(
    body: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新个人档案（PATCH 语义，仅更新传入字段）"""
    data = await UserService.update_profile(user, body, db)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.get("/quota", summary="获取免费分析额度")
async def get_quota(
    request: Request,
    user: User = Depends(get_current_user),
):
    """获取当前用户的免费分析额度状态"""
    data = await UserService.get_quota(user)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.patch("/rating", summary="更新开球网积分")
async def update_rating(
    body: RatingUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新开球网积分，旧积分自动写入历史记录"""
    data = await UserService.update_rating(user, body, db)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.get("/rating-history", summary="积分历史记录")
async def get_rating_history(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """积分历史记录分页查询"""
    data = await UserService.get_rating_history(user, page, page_size, db)
    return success(data=data)


@limiter.limit(RateLimits.DEFAULT)
@router.get("/big-data", summary="乒乓大数据（趣味统计）")
async def get_big_data(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """乒乓大数据（间接胜利算法，24h 缓存）"""
    data = await UserService.get_big_data(user, db)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.delete("/account", summary="用户注销（72h 冷静期）")
async def delete_account(
    body: AccountDeletionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户注销（72h 冷静期内可撤销）"""
    data = await UserService.delete_account(user, body, db)
    return success(data=data.model_dump(), message="注销申请已提交，72 小时内可撤销")


@limiter.limit(RateLimits.DEFAULT)
@router.post("/account/cancel-deletion", summary="撤销注销申请")
async def cancel_deletion(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销用户注销申请（72h 冷静期内）"""
    data = await UserService.cancel_deletion(user, db)
    return success(data=data, message="注销已撤销，账号恢复正常")


@limiter.limit(RateLimits.DEFAULT)
@router.post("/export-data", summary="发起个人数据导出（PIPL）")
async def export_data(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发起个人数据导出（PIPL 数据可携带权，每月限 1 次）"""
    data = await UserService.export_data(user, db)
    return success(data=data.model_dump(), message="导出任务已创建，完成后将通过通知告知您")


@limiter.limit(RateLimits.DEFAULT)
@router.get("/export-data/{task_id}", summary="查询导出状态 + 下载链接")
async def get_export_status(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询导出任务状态和下载链接"""
    data = await UserService.get_export_status(user, task_id, db)
    return success(data=data.model_dump())
