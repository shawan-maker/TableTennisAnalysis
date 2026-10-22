"""
app/api/v1/membership/router.py — 会员模块 API 路由

依据：切片 10-membership/backend.md §6
      API §11 membership 端点（3 个）
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.membership_service import MembershipService

router = APIRouter(prefix="/membership", tags=["会员-等级权益"])


@limiter.limit("100/minute")
@router.get("/tiers", summary="会员等级与权益对比")
async def get_tiers(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询会员等级权益对比表（缓存1h）"""
    data = await MembershipService.get_tiers(db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/current", summary="当前会员状态")
async def get_current_membership(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前会员状态（含到期时间、剩余天数）"""
    data = await MembershipService.get_current_membership(db, user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/quota", summary="今日剩余免费分析次数")
async def get_quota(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询今日剩余免费分析次数（Redis 计数器）"""
    data = await MembershipService.get_quota(db, user.id)
    return success(data=data)
