"""
app/schemas/membership.py — 会员模块 Pydantic Schema

依据：切片 10-membership/backend.md §4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- 响应 Schema ---
class TierBrief(BaseModel):
    """会员等级权益"""
    tier: str
    name: str
    price_monthly_cents: int
    price_quarterly_cents: int
    price_yearly_cents: int
    benefits: list[str]
    quota_config: dict

    model_config = {"from_attributes": True}


class TierListResponse(BaseModel):
    """会员等级列表响应"""
    tiers: list[TierBrief]

    model_config = {"from_attributes": True}


class CurrentMembershipResponse(BaseModel):
    """当前会员状态"""
    tier: str = "free"
    status: str = "none"
    start_at: Optional[str] = None
    expire_at: Optional[str] = None
    days_remaining: int = 0
    auto_renew: bool = False

    model_config = {"from_attributes": True}


class QuotaResponse(BaseModel):
    """今日剩余免费分析次数"""
    tier: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str

    model_config = {"from_attributes": True}


# --- 内部 Schema（供其他模块调用）---
class MembershipCheckResult(BaseModel):
    """会员状态检查结果（供 video_analysis 等模块调用）"""
    tier: str = "free"
    is_member: bool = False
    has_quota: bool = True
    daily_limit: int = 3
    used_today: int = 0
    remaining: int = 3
