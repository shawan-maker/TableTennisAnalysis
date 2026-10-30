"""
app/api/v1/notification/router.py — 通知模块 API 路由

依据：切片 12-notification/backend.md §6
      API §13 notification 端点（4 个）
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.notification import (
    MarkReadRequest, SubscribeRequest, NotificationListQuery,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notification", tags=["通知"])


@router.get("/list", summary="通知列表")
@limiter.limit("100/minute")
async def list_notifications(
    request: Request,
    is_read: Optional[bool] = Query(default=None),
    type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """查询通知列表（分页）"""
    query = NotificationListQuery(
        is_read=is_read, type=type, page=page, page_size=page_size,
    )
    data = await NotificationService.list_notifications(user.id, query)
    return success(data=data)


@router.post("/read", summary="标记已读")
@limiter.limit("100/minute")
async def mark_read(
    body: MarkReadRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """批量标记通知为已读"""
    data = await NotificationService.mark_read(user.id, body.notification_ids)
    return success(data=data, message="已标记为已读")


@router.post("/subscribe", summary="微信订阅消息授权")
@limiter.limit("100/minute")
async def subscribe(
    body: SubscribeRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """微信订阅消息授权"""
    data = await NotificationService.subscribe_templates(user.id, body.template_ids)
    return success(data=data, message="订阅已更新")


@router.get("/unread-count", summary="未读通知数量")
@limiter.limit("100/minute")
async def unread_count(
    request: Request,
    user: User = Depends(get_current_user),
):
    """获取未读通知数量"""
    count = await NotificationService.get_unread_count(user.id)
    return success(data={"unread_count": count})
