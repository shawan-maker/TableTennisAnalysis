"""
app/api/v1/video_analysis/router.py — 视频分析模块 API 路由

依据：API §4 / 切片 03-video_analysis/backend.md §6
S3 实现：11 个端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.schemas.video_analysis import (
    CreateTaskRequest,
    FeedbackRequest,
    UploadCompleteRequest,
    UploadTokenRequest,
)
from app.services.video_analysis_service import VideoAnalysisService

router = APIRouter(prefix="/video-analysis", tags=["视频分析"])

# 独立分享路由 — 不挂载 /video-analysis prefix，挂载到 /share/{share_token} 根路径
share_router = APIRouter(tags=["分享"])


# =============================================================================
# 上传
# =============================================================================

@limiter.limit(RateLimits.DEFAULT)
@router.post("/upload-token", summary="获取上传凭证")
async def get_upload_token(
    body: UploadTokenRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """获取 OSS STS 直传凭证 + object key"""
    data = await VideoAnalysisService.get_upload_token(user.id, body)
    return success(data=data, message="上传凭证已签发")


@limiter.limit(RateLimits.DEFAULT)
@router.post("/upload-complete", summary="上传完成确认")
async def confirm_upload(
    body: UploadCompleteRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """上传完成确认 — HEAD Object 校验"""
    data = await VideoAnalysisService.confirm_upload(user.id, body)
    return success(data=data, message="文件已确认")


# =============================================================================
# 任务
# =============================================================================

@limiter.limit("10/hour")
@router.post("/tasks", summary="创建分析任务")
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建分析任务（免费 3 次/天，会员不限）"""
    data = await VideoAnalysisService.create_task(user.id, body)
    return success(data=data, message="分析任务已创建")


@limiter.limit(RateLimits.DEFAULT)
@router.get("/tasks", summary="任务列表")
async def list_tasks(
    request: Request,
    status: Optional[str] = Query(default=None, description="状态过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """任务列表（分页）"""
    data = await VideoAnalysisService.list_tasks(user.id, status, page, page_size)
    return success(data=data)


@limiter.limit(RateLimits.DEFAULT)
@router.get("/tasks/{task_id}", summary="任务详情")
async def get_task_detail(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
):
    """任务详情 + 进度"""
    data = await VideoAnalysisService.get_task_detail(user.id, task_id)
    return success(data=data)


# =============================================================================
# 报告
# =============================================================================

@limiter.limit(RateLimits.DEFAULT)
@router.get("/reports", summary="报告列表")
async def list_reports(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """报告列表（分页）"""
    data = await VideoAnalysisService.list_reports(user.id, page, page_size)
    return success(data=data)


@limiter.limit(RateLimits.DEFAULT)
@router.get("/reports/{report_id}", summary="报告详情")
async def get_report_detail(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    """分析报告详情（含完整结果数据 + 报告文字）"""
    data = await VideoAnalysisService.get_report_detail(user.id, report_id)
    return success(data=data)


@limiter.limit(RateLimits.DEFAULT)
@router.post("/reports/{report_id}/feedback", summary="提交反馈")
async def submit_feedback(
    report_id: int,
    body: FeedbackRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """提交报告反馈（正确/不正确，可覆盖）"""
    data = await VideoAnalysisService.submit_feedback(user.id, report_id, body)
    return success(data=data, message="反馈已提交")


@limiter.limit(RateLimits.DEFAULT)
@router.get("/reports/{report_id}/feedbacks", summary="反馈历史")
async def list_feedbacks(
    request: Request,
    report_id: int,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """获取报告的反馈历史列表（分页）"""
    data = await VideoAnalysisService.list_feedbacks(user.id, report_id, page, page_size)
    return success(data=data)


@limiter.limit(RateLimits.DEFAULT)
@router.get("/reports/{report_id}/annotated-video", summary="标注视频 URL")
async def get_annotated_video(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    """获取标注视频 CDN URL"""
    data = await VideoAnalysisService.get_annotated_video(user.id, report_id)
    return success(data=data)


@limiter.limit("5/day")
@router.post("/reports/{report_id}/share", summary="创建分享")
async def create_share(
    report_id: int,
    request: Request,
    user: User = Depends(get_current_user),
):
    """生成分享链接（7 天有效，每天限 5 次）"""
    data = await VideoAnalysisService.create_share(user.id, report_id)
    return success(data=data, message="分享链接已创建")


# =============================================================================
# 公开分享（不需要认证）— 挂载到根路径 /share/{share_token}
# =============================================================================

@limiter.limit(RateLimits.DEFAULT)
@share_router.get("/share/{share_token}", summary="公开分享报告")
async def get_shared_report(
    share_token: str,
    request: Request,
):
    """获取公开分享报告摘要（7 天有效，不含训练建议/趋势/个人信息）"""
    data = await VideoAnalysisService.get_shared_report(share_token)
    return success(data=data)
