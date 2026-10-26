"""
app/schemas/user.py — 用户模块 Pydantic Schema

依据：API §3 user 端点契约 / 切片 02-user/backend.md §3
规范：{Entity}Request / {Entity}Response 命名
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# 请求 Schema
# =============================================================================

# R4-User-2: 添加 @field_validator 校验 playing_style/self_assessed_level
# R4-User-3: 移除 kqs_rating/kqs_username/nickname/avatar_url（这些通过 /users/rating 或 /users/profile 单独端点更新）
class ProfileUpdateRequest(BaseModel):
    """更新个人档案请求（PATCH 语义，仅更新传入字段）"""

    playing_style: Optional[str] = Field(default=None, max_length=32, description="打法类型")
    self_assessed_level: Optional[str] = Field(default=None, max_length=32, description="自评水平")
    equipment_config: Optional[dict] = Field(default=None, description="装备配置 JSON")

    @field_validator("playing_style")
    @classmethod
    def validate_playing_style(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"loop", "fast_attack", "chop", "all_round"}
        if v not in allowed:
            raise ValueError(f"打法类型不合法，可选值: {', '.join(sorted(allowed))}")
        return v

    @field_validator("self_assessed_level")
    @classmethod
    def validate_self_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"beginner", "intermediate", "advanced"}
        if v not in allowed:
            raise ValueError(f"自评水平不合法，可选值: {', '.join(sorted(allowed))}")
        return v


class RatingUpdateRequest(BaseModel):
    """更新积分请求"""

    rating: int = Field(..., ge=500, le=3000, description="积分值")
    # R4-User-4: max_length=128 → 64（DB 列 VARCHAR(64)）
    kqs_username: Optional[str] = Field(default=None, max_length=64, description="开球网用户名")
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

    id: int
    profile_completeness: int
    updated_fields: list[str]


class RatingUpdateResponse(BaseModel):
    """更新积分响应"""

    id: int
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
