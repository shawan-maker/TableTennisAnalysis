"""
app/schemas/notification.py — 通知模块 Pydantic Schema

依据：切片 12-notification/backend.md §4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.core.pagination import Paginated


# --- 请求 Schema ---
class MarkReadRequest(BaseModel):
    """标记已读请求"""
    notification_ids: list[int] = Field(..., min_length=1, max_length=100)


class SubscribeRequest(BaseModel):
    """微信订阅消息授权请求"""
    template_ids: list[str] = Field(..., min_length=1)


# --- 响应 Schema ---
class NotificationBrief(BaseModel):
    """通知摘要"""
    id: int
    type: str
    title: str
    content: Optional[str] = None
    is_read: bool
    extra_data: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class MarkReadResponse(BaseModel):
    """标记已读响应"""
    updated_count: int


class SubscribeResponse(BaseModel):
    """订阅授权响应"""
    subscribed_templates: list[str]


# --- 查询 Schema ---
class NotificationListQuery(BaseModel):
    """通知列表查询参数"""
    is_read: Optional[bool] = None
    type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# --- 分页包装 ---
PaginatedNotifications = Paginated[NotificationBrief]
