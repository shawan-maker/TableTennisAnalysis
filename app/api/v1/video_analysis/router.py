"""
app/api/v1/video_analysis/router.py — 视频分析模块 API 路由

依据：API §4 / 切片 03-video_analysis/backend.md §6
S3 实现：11 个端点
"""

from typing import Optional

import html as _html
import json as _json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
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

@router.post("/upload-token", summary="获取上传凭证")
@limiter.limit(RateLimits.DEFAULT)
async def get_upload_token(
    body: UploadTokenRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """获取 OSS STS 直传凭证 + object key"""
    data = await VideoAnalysisService.get_upload_token(user.id, body)
    return success(data=data, message="上传凭证已签发")


@router.post("/upload-complete", summary="上传完成确认")
@limiter.limit(RateLimits.DEFAULT)
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

@router.post("/tasks", summary="创建分析任务")
@limiter.limit("10/hour")
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建分析任务（免费 3 次/天，会员不限）"""
    data = await VideoAnalysisService.create_task(user.id, body)
    return success(data=data, message="分析任务已创建")


@router.get("/tasks", summary="任务列表")
@limiter.limit(RateLimits.DEFAULT)
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


@router.get("/tasks/{task_id}", summary="任务详情")
@limiter.limit(RateLimits.DEFAULT)
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

@router.get("/reports", summary="报告列表")
@limiter.limit(RateLimits.DEFAULT)
async def list_reports(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """报告列表（分页）"""
    data = await VideoAnalysisService.list_reports(user.id, page, page_size)
    return success(data=data)


@router.get("/reports/{report_id}", summary="报告详情")
@limiter.limit(RateLimits.DEFAULT)
async def get_report_detail(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    """分析报告详情（含完整结果数据 + 报告文字）"""
    data = await VideoAnalysisService.get_report_detail(user.id, report_id)
    return success(data=data)


@router.post("/reports/{report_id}/feedback", summary="提交反馈")
@limiter.limit(RateLimits.DEFAULT)
async def submit_feedback(
    report_id: int,
    body: FeedbackRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """提交报告反馈（正确/不正确，可覆盖）"""
    data = await VideoAnalysisService.submit_feedback(user.id, report_id, body)
    return success(data=data, message="反馈已提交")


@router.get("/reports/{report_id}/feedbacks", summary="反馈历史")
@limiter.limit(RateLimits.DEFAULT)
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


@router.get("/reports/{report_id}/annotated-video", summary="标注视频 URL")
@limiter.limit(RateLimits.DEFAULT)
async def get_annotated_video(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    """获取标注视频 CDN URL"""
    data = await VideoAnalysisService.get_annotated_video(user.id, report_id)
    return success(data=data)


@router.post("/reports/{report_id}/share", summary="创建分享")
@limiter.limit("5/day")
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

def _render_share_page(data: dict) -> str:
    """R12-VA-3: 渲染分享摘要 HTML 页（API §4.11 要求非 JSON）

    设计要求内容：封面/标注视频、技术统计、落点热图、文字摘要（summary +
    top 2 issues）、球速范围；不含训练建议/历史趋势/个人信息（service 层
    已过滤安全子集）。文本经 html.escape 防 XSS；图表数据以 JSON island
    嵌入供前端图表库水合。
    """
    e = _html.escape
    summary = e(data.get("report_summary") or "")
    issues = data.get("top_issues") or []
    result_data = data.get("result_data") or {}
    technique_stats = result_data.get("technique_stats") or {}
    ball_speed = result_data.get("ball_speed")

    issue_items = "".join(
        f"<li class='issue'>{e(str(item))}</li>" for item in issues
    )

    stat_rows = "".join(
        f"<div class='stat-row'><span class='stat-name'>{e(str(k))}</span>"
        f"<span class='stat-value'>{e(str(v))}</span></div>"
        for k, v in technique_stats.items()
    ) or "<p class='empty'>暂无统计数据</p>"

    cover = data.get("cover_image_url")
    video_url = data.get("annotated_video_url")
    video_block = (
        f"<video controls playsinline poster='{e(str(cover))}' src='{e(str(video_url))}'></video>"
        if video_url
        else (
            f"<img alt='视频封面' src='{e(str(cover))}'/>" if cover else "<p class='empty'>视频处理中</p>"
        )
    )

    speed_block = (
        f"<span class='stat-value'>{e(str(ball_speed))}</span>"
        if ball_speed is not None
        else "<p class='empty'>暂无球速数据</p>"
    )

    # 图表数据 JSON island：技术统计环形图 + 落点热图由前端图表库水合渲染
    chart_data = _json.dumps(
        {"technique_stats": technique_stats,
         "landing_points": result_data.get("landing_points")},
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI 乒乓分析报告分享</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f6f8;color:#182b32}}
 .card{{background:#fff;margin:16px auto;max-width:640px;padding:20px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
 video,img{{width:100%;border-radius:8px;display:block}}
 h1{{font-size:20px;margin:0 0 8px}}
 .section{{margin-top:20px}}
 .section h2{{font-size:16px;color:#0f7b6c;margin:0 0 8px}}
 .stat-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed #eee;font-size:14px}}
 .issue{{font-size:14px;line-height:1.6;margin:4px 0}}
 .empty{{font-size:13px;color:#9aa5ab}}
 footer{{text-align:center;font-size:12px;color:#9aa5ab;padding:12px}}
</style>
</head>
<body>
<div class="card">
  <h1>AI 乒乓分析报告</h1>
  <div class="section media">{video_block}</div>
  <div class="section"><h2>报告摘要</h2><p class="summary">{summary or "暂无摘要"}</p></div>
  <div class="section"><h2>主要问题</h2><ul>{issue_items or "<li class='empty'>暂无</li>"}</ul></div>
  <div class="section"><h2>技术统计</h2>{stat_rows}</div>
  <div class="section"><h2>球速数据</h2>{speed_block}</div>
</div>
<footer>报告由 AI 乒乓助手的用户分享生成，仅供参考</footer>
<script id="share-chart-data" type="application/json">{_html.escape(chart_data)}</script>
</body>
</html>"""


@share_router.get("/share/{share_token}", summary="公开分享报告", response_class=HTMLResponse)
@limiter.limit(RateLimits.DEFAULT)
async def get_shared_report(
    share_token: str,
    request: Request,
):
    """获取公开分享报告摘要页（HTML 渲染，7 天有效，不含训练建议/趋势/个人信息）"""
    data = await VideoAnalysisService.get_shared_report(share_token)
    # R12-VA-3: API §4.11 要求返回 HTML 渲染页面（非 JSON API）
    return HTMLResponse(content=_render_share_page(data))
