"""
app/schemas/user.py — 用户模块 Pydantic Schema

依据：API §3 user 端点契约 / 切片 02-user/backend.md §3
规范：{Entity}Request / {Entity}Response 命名
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# 请求 Schema
# =============================================================================

class UpdateProfileRequest(BaseModel):
    """更新个人档案请求"""

    playing_style: Optional[str] = Field(default=None, max_length=32, description="打法类型")
    self_assessed_level: Optional[str] = Field(default=None, max_length=32, description="自评水平")
    equipment_config: Optional[dict] = Field(default=None, description="装备配置 JSON")
    kqs_rating: Optional[int] = Field(default=None, ge=0, le=3000, description="开球网积分")
    kqs_username: Optional[str] = Field(default=None, max_length=64, description="开球网用户名")
    nickname: Optional[str] = Field(default=None, max_length=64, description="昵称")
    avatar_url: Optional[str] = Field(default=None, max_length=512, description="头像 URL")


class UpdateRatingRequest(BaseModel):
    """更新积分请求"""

    rating: int = Field(..., ge=0, le=3000, description="积分值")
    source: str = Field(default="manual", max_length=20, description="来源")


# =============================================================================
# 响应 Schema
# =============================================================================

class ProfileResponse(BaseModel):
    """个人档案响应"""

    id: int
    nickname: str
    avatar_url: Optional[str] = None
    status: str
    playing_style: Optional[str] = None
    self_assessed_level: Optional[str] = None
    equipment_config: Optional[dict] = None
    kqs_rating: Optional[int] = None
    kqs_username: Optional[str] = None
    profile_completeness: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UpdateProfileResponse(BaseModel):
    """更新档案响应"""

    profile_completeness: int
    updated_fields: list[str]


class UpdateRatingResponse(BaseModel):
    """更新积分响应"""

    old_rating: Optional[int]
    new_rating: int
    history_id: int


class RatingHistoryItem(BaseModel):
    """积分历史记录项"""

    id: int
    rating: int
    source: str
    recorded_at: datetime

    model_config = {"from_attributes": True}


class QuotaResponse(BaseModel):
    """免费额度响应"""

    daily_limit: int = 3
    used_today: int = 0
    remaining: int = 3
    reset_at: Optional[str] = None  # 下次重置时间
