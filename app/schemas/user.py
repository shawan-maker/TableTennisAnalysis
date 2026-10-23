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

class ProfileUpdateRequest(BaseModel):
    """更新个人档案请求（PATCH 语义，仅更新传入字段）"""

    playing_style: Optional[str] = Field(default=None, max_length=32, description="打法类型")
    self_assessed_level: Optional[str] = Field(default=None, max_length=32, description="自评水平")
    equipment_config: Optional[dict] = Field(default=None, description="装备配置 JSON")
    kqs_rating: Optional[int] = Field(default=None, ge=0, le=3000, description="开球网积分")
    kqs_username: Optional[str] = Field(default=None, max_length=64, description="开球网用户名")
    nickname: Optional[str] = Field(default=None, max_length=64, description="昵称")
    avatar_url: Optional[str] = Field(default=None, max_length=512, description="头像 URL")


class RatingUpdateRequest(BaseModel):
    """更新积分请求"""

    rating: int = Field(..., ge=500, le=3000, description="积分值")
    kqs_username: Optional[str] = Field(default=None, max_length=128, description="开球网用户名")
    source: str = Field(default="manual", max_length=20, description="来源")


class AccountDeletionRequest(BaseModel):
    """用户注销请求"""

    reason: Optional[str] = Field(default=None, max_length=500, description="注销原因")
    confirmation: str = Field(..., description="必须为 'DELETE_ACCOUNT_CONFIRM'")


# =============================================================================
# 响应 Schema
# =============================================================================

class UserProfileResponse(BaseModel):
    """个人档案响应 — 嵌套结构（设计 §3.1）"""

    id: int
    nickname: str
    avatar_url: Optional[str] = None
    profile: dict = Field(default_factory=dict, description="kqs_rating/kqs_username/playing_style/self_assessed_level/equipment_config/profile_completeness")

    model_config = {"from_attributes": True}


class ProfileUpdateResponse(BaseModel):
    """更新档案响应"""

    profile_completeness: int
    updated_fields: list[str]


class RatingUpdateResponse(BaseModel):
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


class BigDataResponse(BaseModel):
    """乒乓大数据（趣味统计）响应"""

    highest_win_rating: Optional[int] = None
    win_streak: int = 0
    match_cities: int = 0
    total_opponents: int = 0
    indirect_wins: list[str] = []
    total_matches: int = 0
    win_rate: float = 0.0
    favorite_shot: Optional[str] = None


class AccountDeletionResponse(BaseModel):
    """注销申请响应"""

    scheduled_deletion_at: datetime
    can_cancel_before: datetime


class ExportCreateResponse(BaseModel):
    """导出任务创建响应"""

    task_id: str
    status: str  # pending


class ExportStatusResponse(BaseModel):
    """导出任务状态响应"""

    task_id: str
    status: str  # pending/processing/completed/failed
    download_url: Optional[str] = None
    expire_at: Optional[datetime] = None
    file_size: Optional[int] = None


class PaginatedRatingHistory(BaseModel):
    """积分历史分页响应"""

    total: int
    page: int
    page_size: int
    items: list[RatingHistoryItem]
