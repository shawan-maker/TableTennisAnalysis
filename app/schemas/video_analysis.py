"""
app/schemas/video_analysis.py — 视频分析模块 Pydantic Schema

依据：API §4 / 切片 03-video_analysis/backend.md §4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from typing import Literal


# =============================================================================
# 请求 Schema
# =============================================================================

class UploadTokenRequest(BaseModel):
    """获取上传凭证请求"""
    filename: str = Field(..., min_length=1, max_length=255, description="文件名")
    file_size: int = Field(..., ge=1048576, le=524288000, description="文件大小（字节，1MB-500MB）")

    @field_validator("filename")
    @classmethod
    def validate_file_extension(cls, v: str) -> str:
        """R6-Video-2: 文件类型校验 — 仅支持 MP4/MOV 格式"""
        ext = v.rsplit(".", 1)[-1].lower() if "." in v else ""
        if ext not in ("mp4", "mov"):
            raise ValueError("仅支持 MP4/MOV 格式")
        return v


class UploadCompleteRequest(BaseModel):
    """上传完成确认请求"""
    file_id: int = Field(..., ge=1, description="文件 ID")


class CreateTaskRequest(BaseModel):
    """创建分析任务请求"""
    file_id: int = Field(..., ge=1, description="文件 ID")
    oss_key: str = Field(..., min_length=1, description="OSS 对象键")


class FeedbackRequest(BaseModel):
    """提交反馈请求"""
    is_correct: bool = Field(..., description="报告是否准确")
    comment: Optional[str] = Field(default=None, max_length=500, description="反馈评论")


# =============================================================================
# 响应 Schema
# =============================================================================

class StsCredentials(BaseModel):
    """STS 临时凭证"""
    access_key_id: str
    access_key_secret: str
    security_token: str
    expiration: str
    bucket: str
    endpoint: str


class UploadTokenResponse(BaseModel):
    """上传凭证响应"""
    file_id: int
    oss_key: str
    sts_credentials: StsCredentials
    upload_url: str
    expire_at: str


class UploadCompleteResponse(BaseModel):
    """上传完成响应"""
    file_id: int
    ready: bool
    actual_size: int
    duration_sec: Optional[int] = None


class CreateTaskResponse(BaseModel):
    """创建任务响应"""
    task_id: int
    task_uuid: str
    status: str = "queued"
    estimated_wait_minutes: int = 3


class TaskListItem(BaseModel):
    """任务列表项"""
    task_id: int
    task_uuid: str
    status: str
    current_step: int
    total_steps: int
    progress: float
    created_at: Optional[datetime] = None
    report_id: Optional[int] = None
    cover_image_url: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskDetailResponse(BaseModel):
    """任务详情"""
    task_id: int
    task_uuid: str
    status: str
    current_step: int
    total_steps: int
    step_name: Optional[str] = None
    progress: float
    estimated_remaining_seconds: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    report_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    """报告列表项"""
    id: int
    task_id: int
    created_at: Optional[datetime] = None
    is_llm_generated: bool
    cover_image_url: Optional[str] = None
    report_summary: Optional[str] = None

    model_config = {"from_attributes": True}


class ReportDetailResponse(BaseModel):
    """报告详情"""
    id: int
    task_id: int
    task_uuid: Optional[str] = None
    created_at: Optional[datetime] = None
    is_llm_generated: bool
    is_readonly: bool = False
    result_data: dict
    report_text: dict
    annotated_video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    report_images: Optional[dict] = None

    model_config = {"from_attributes": True}


class FeedbackResponse(BaseModel):
    """反馈响应"""
    feedback_id: int
    is_correct: bool
    data_flywheel_action: str  # archived/manual_review


class FeedbackHistoryItem(BaseModel):
    """反馈历史项"""
    id: int
    report_id: int
    report_title: Optional[str] = None
    is_correct: bool
    comment: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnnotatedVideoResponse(BaseModel):
    """标注视频响应"""
    url: str
    duration_sec: Optional[int] = None
    quality_options: list[str] = Field(default_factory=list)


class ShareResponse(BaseModel):
    """分享响应"""
    share_url: str
    card_image_url: Optional[str] = None
    expire_at: str


class SharedReportSummary(BaseModel):
    """公开分享报告摘要（不含训练建议/趋势/个人信息）"""
    report_id: int
    cover_image_url: Optional[str] = None
    annotated_video_url: Optional[str] = None
    result_data: dict  # 仅含 safe 字段
    report_text: dict  # summary + top 2 issues（向后兼容）
    report_summary: str = ""  # R6-Video-3: 扁平化摘要
    top_issues: list[str] = Field(default_factory=list)  # R6-Video-3: 扁平化 top issues
    created_at: Optional[datetime] = None
