"""
tests/unit/test_video_analysis.py — S3 视频分析模块单元测试

覆盖：
- 上传凭证/确认流程
- 任务创建 + 10 步 mock 流水线 e2e
- 任务/报告列表 + 详情
- 反馈提交/覆盖
- 分享创建/公开访问
- 配额限制
"""

import os
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.video_analysis import AnalysisReport, FileRecord, PipelineStep, VideoTask
from app.services.file_service import FileService


# =============================================================================
# 辅助函数
# =============================================================================

async def _create_and_upload_file(client, headers, filename="test.mp4", file_size=10 * 1024 * 1024):
    """完整上传流程：获取凭证 → 保存 mock 文件 → 确认上传"""
    # 1. 获取上传凭证
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": filename, "file_size": file_size},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    file_id = data["file_id"]
    oss_key = data["oss_key"]

    # 2. 保存 mock 文件到本地（模拟 OSS 上传）— 大小必须与声明一致
    FileService.save_uploaded_file(oss_key, b"\x00" * file_size)

    # 3. 确认上传
    resp = await client.post(
        "/api/v1/video-analysis/upload-complete",
        json={"file_id": file_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["ready"] is True

    return file_id, oss_key


# =============================================================================
# 上传凭证测试
# =============================================================================

@pytest.mark.asyncio
async def test_upload_token_valid(client, auth_headers):
    """获取上传凭证 — 正常请求"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "match.mp4", "file_size": 10 * 1024 * 1024},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "file_id" in data
    assert "oss_key" in data
    assert "sts_credentials" in data
    assert "upload_url" in data
    assert data["oss_key"].startswith("videos/raw/")


@pytest.mark.asyncio
async def test_upload_token_invalid_type(client, auth_headers):
    """获取上传凭证 — 不支持的文件类型（R12-VA-4: API §4.1 规定 400）"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "match.avi", "file_size": 10 * 1024 * 1024},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "仅支持" in resp.json()["message"]


@pytest.mark.asyncio
async def test_upload_token_too_large(client, auth_headers):
    """获取上传凭证 — 文件过大（R12-VA-4: API §4.1 规定 400）"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "match.mp4", "file_size": 600 * 1024 * 1024},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "不能超过 500MB" in resp.json()["message"]


@pytest.mark.asyncio
async def test_upload_token_too_small(client, auth_headers):
    """获取上传凭证 — 文件过小（R12-VA-4: API §4.1 规定 422）"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "match.mp4", "file_size": 500 * 1024},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不能小于 1MB" in resp.json()["message"]


@pytest.mark.asyncio
async def test_upload_token_no_auth(client):
    """获取上传凭证 — 无认证"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "match.mp4", "file_size": 10 * 1024 * 1024},
    )
    assert resp.status_code == 401


# =============================================================================
# 上传确认测试
# =============================================================================

@pytest.mark.asyncio
async def test_upload_complete_not_uploaded(client, auth_headers):
    """上传确认 — 文件尚未上传（HEAD Object 找不到）"""
    # 获取凭证但不保存文件
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "test.mp4", "file_size": 10 * 1024 * 1024},
        headers=auth_headers,
    )
    file_id = resp.json()["data"]["file_id"]

    # 直接确认上传（文件不存在）
    resp = await client.post(
        "/api/v1/video-analysis/upload-complete",
        json={"file_id": file_id},
        headers=auth_headers,
    )
    # R12-VA-5: API §4.2 错误表 — OSS 文件不存在为 404
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_complete_success(client, auth_headers):
    """上传确认 — 正常流程（内联执行以断言 confirm 响应体）"""
    # 1. 获取上传凭证
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "test.mp4", "file_size": 10 * 1024 * 1024},
        headers=auth_headers,
    )
    data = resp.json()["data"]
    file_id, oss_key = data["file_id"], data["oss_key"]

    # 2. 保存 mock 文件（模拟 OSS 上传）
    FileService.save_uploaded_file(oss_key, b"\x00" * (10 * 1024 * 1024))

    # 3. 确认上传
    resp = await client.post(
        "/api/v1/video-analysis/upload-complete",
        json={"file_id": file_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    confirm_data = resp.json()["data"]
    assert confirm_data["ready"] is True
    # R12-VA-6: duration_sec 在响应中返回（5-600 校验值；不入 file_record，
    # create_task 时写入 video_task.duration_sec 供 ai_pipeline 读取）
    assert confirm_data["duration_sec"] is not None

    # 验证 file_record 状态
    async with async_session_factory() as db:
        record = await db.get(FileRecord, file_id)
        assert record.status == "uploaded"
        assert record.oss_etag is not None
        assert record.actual_size is not None


# =============================================================================
# 任务创建 + 流水线 e2e 测试
# =============================================================================

@pytest.mark.asyncio
async def test_create_task_and_pipeline(client, auth_headers):
    """创建任务 + 10 步 mock 流水线完整执行"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)

    # 创建任务（eager 模式下流水线同步执行完毕）
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    task_id = data["task_id"]
    assert data["status"] == "queued"
    assert "task_uuid" in data

    # 验证任务已完成（pipeline 同步执行完毕）
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "completed"
        assert task.progress == 1.0  # R4: progress 从 0-100 改为 0.0-1.0
        assert task.current_step == 10

        # 验证 10 条 pipeline_step 记录
        from sqlalchemy import select
        steps_result = await db.execute(
            select(PipelineStep)
            .where(PipelineStep.task_id == task_id)
            .order_by(PipelineStep.step_number)
        )
        steps = steps_result.scalars().all()
        assert len(steps) == 10
        for i, step in enumerate(steps):
            assert step.step_number == i + 1
            assert step.status == "completed"
            assert step.duration_ms is not None

        # 验证分析报告已生成
        report_result = await db.execute(
            select(AnalysisReport).where(AnalysisReport.task_id == task_id)
        )
        report = report_result.scalar_one_or_none()
        assert report is not None
        assert "summary" in report.report_text
        assert "issues" in report.report_text
        assert "suggestions" in report.report_text
        assert "video_info" in report.result_data
        assert "technique_stats" in report.result_data
        assert "landing_points" in report.result_data
        assert report.is_llm_generated is False  # LLM_ENABLED=False
        assert report.annotated_video_url is not None


# =============================================================================
# 任务列表/详情测试
# =============================================================================

@pytest.mark.asyncio
async def test_list_tasks(client, auth_headers):
    """任务列表 — 分页 + 状态过滤"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)

    # 创建 2 个任务
    for _ in range(2):
        resp = await client.post(
            "/api/v1/video-analysis/tasks",
            json={"file_id": file_id, "oss_key": oss_key},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    # 列表
    resp = await client.get(
        "/api/v1/video-analysis/tasks?page=1&page_size=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    assert "report_id" in data["items"][0]

    # 状态过滤
    resp = await client.get(
        "/api/v1/video-analysis/tasks?status=completed&page=1&page_size=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(item["status"] == "completed" for item in data["items"])


@pytest.mark.asyncio
async def test_task_detail(client, auth_headers):
    """任务详情"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    # 正常请求
    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_id"] == task_id  # R4: 字段名 id → task_id
    assert data["status"] == "completed"
    assert data["progress"] == 1.0  # R4: progress 从 0-100 改为 0.0-1.0
    assert data["report_id"] is not None

    # 404
    resp = await client.get(
        "/api/v1/video-analysis/tasks/99999",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# =============================================================================
# 报告测试
# =============================================================================

@pytest.mark.asyncio
async def test_report_list_and_detail(client, auth_headers):
    """报告列表 + 详情"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    # 获取 report_id
    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    report_id = resp.json()["data"]["report_id"]

    # 报告列表
    resp = await client.get(
        "/api/v1/video-analysis/reports?page=1&page_size=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert any(item["id"] == report_id for item in data["items"])

    # 报告详情
    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == report_id
    assert "result_data" in data
    assert "report_text" in data
    assert "summary" in data["report_text"]
    assert data["is_llm_generated"] is False

    # 404
    resp = await client.get(
        "/api/v1/video-analysis/reports/99999",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# =============================================================================
# 反馈测试
# =============================================================================

@pytest.mark.asyncio
async def test_feedback_create_and_update(client, auth_headers):
    """反馈 — 创建 + 覆盖更新"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    report_id = resp.json()["data"]["report_id"]

    # 创建反馈
    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/feedback",
        json={"is_correct": False, "comment": "落点检测不准确"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_correct"] is False
    assert data["data_flywheel_action"] == "manual_review"
    feedback_id = data["feedback_id"]

    # 覆盖更新
    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/feedback",
        json={"is_correct": True, "comment": "重新看了一下，挺准的"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_correct"] is True
    assert data["data_flywheel_action"] == "archived"
    # 同一条记录（覆盖）
    assert data["feedback_id"] == feedback_id

    # 404 — 报告不存在
    resp = await client.post(
        "/api/v1/video-analysis/reports/99999/feedback",
        json={"is_correct": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_feedbacks(client, auth_headers):
    """反馈历史列表"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    report_id = resp.json()["data"]["report_id"]

    # 提交反馈
    await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/feedback",
        json={"is_correct": True, "comment": "很准"},
        headers=auth_headers,
    )

    # 查询反馈历史
    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}/feedbacks",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert len(data["items"]) >= 1
    item = data["items"][0]
    assert item["report_id"] == report_id
    assert item["is_correct"] is True
    assert item["comment"] == "很准"
    assert "report_title" in item
    assert "status" in item
    assert "created_at" in item

    # 404 — 报告不存在
    resp = await client.get(
        "/api/v1/video-analysis/reports/99999/feedbacks",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_validation_422(client, auth_headers):
    """R12-VA-12: feedback 请求校验 — 缺 is_correct / comment 超长 → 422

    Pydantic 层先行拦截（FeedbackRequest: is_correct 必填 bool，
    comment max_length=500），不进入业务层 — 无需真实报告种子。
    """
    # 缺 is_correct（必填字段）→ 422
    resp = await client.post(
        "/api/v1/video-analysis/reports/99999/feedback",
        json={"comment": "缺必填字段"},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # comment 501 字符（max_length=500）→ 422
    resp = await client.post(
        "/api/v1/video-analysis/reports/99999/feedback",
        json={"is_correct": True, "comment": "x" * 501},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # 对照：500 字符边界合法（业务层 404 报告不存在，而非 422 校验错误）
    resp = await client.post(
        "/api/v1/video-analysis/reports/99999/feedback",
        json={"is_correct": True, "comment": "x" * 500},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# =============================================================================
# 标注视频测试
# =============================================================================

@pytest.mark.asyncio
async def test_annotated_video(client, auth_headers):
    """获取标注视频 URL"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    report_id = resp.json()["data"]["report_id"]

    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}/annotated-video",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "url" in data  # R4: 字段名 annotated_video_url → url
    assert data["url"].startswith("http")


# =============================================================================
# 分享测试
# =============================================================================

@pytest.mark.asyncio
async def test_share_create_and_access(client, auth_headers):
    """分享 — 创建 + 公开访问"""
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["task_id"]

    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}",
        headers=auth_headers,
    )
    report_id = resp.json()["data"]["report_id"]

    # 创建分享
    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/share",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "share_url" in data
    assert "expire_at" in data
    share_token = data["share_url"].split("/share/")[-1]

    # 公开访问（不需要认证）— R12-VA-1: share_router 挂载根路径 /share/
    # R12-VA-3: API §4.11 要求 HTML 渲染页（非 JSON API）
    resp = await client.get(
        f"/share/{share_token}",
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    page = resp.text
    # 页面关键区块：标题/摘要/技术统计/球速/图表数据 JSON island
    assert "AI 乒乓分析报告" in page
    assert "报告摘要" in page
    assert "技术统计" in page
    assert "球速数据" in page
    assert 'id="share-chart-data"' in page
    # 分享页不含训练建议（service 安全子集已过滤，页面不得泄露）
    assert "training_suggestions" not in page
    assert "训练建议" not in page

    # 无效 token
    # R12-VA-7: 使用真实挂载路径，此前 /api/v1/video-analysis/share/ 为不存在路径，
    # 404 来自路由缺失而非 token 校验（假阳性）
    resp = await client.get(
        "/share/invalid_token_12345",
    )
    assert resp.status_code == 404


# =============================================================================
# 配额限制测试
# =============================================================================

@pytest.mark.asyncio
async def test_quota_limit(client, auth_headers):
    """免费配额 — 超过 3 次/天被拒"""
    # 预填充 Redis 配额计数器到上限
    redis = await get_redis()
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    # 获取 test_user 的 user_id
    from app.core.security import generate_jti
    from app.core.security import create_access_token
    # auth_headers 中有 access_token，但我们需要 user_id
    # 直接从 JWT 解析或使用 fixture
    # 简单方式：直接调用 service 层
    from app.services.video_analysis_service import VideoAnalysisService
    from app.schemas.video_analysis import UploadTokenRequest

    # 创建第一个文件并完成上传
    file_id, oss_key = await _create_and_upload_file(client, auth_headers)

    # 获取 user_id
    from app.models.user import User
    from sqlalchemy import select
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.openid == "test_openid_001"))
        user = result.scalar_one_or_none()
        user_id = user.id

    # 预填充配额到 3（已用完）
    key = f"quota:analysis:{user_id}:{today}"
    await redis.set(key, 3)

    # 第 4 次创建任务应该被拒
    resp = await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=auth_headers,
    )
    assert resp.status_code == 429


# =============================================================================
# FileService 单元测试
# =============================================================================

@pytest.mark.asyncio
async def test_file_service_mock():
    """FileService mock 模式基本功能"""
    # 生成 OSS Key
    key = FileService.generate_oss_key(1, "test.mp4")
    assert key.startswith("videos/raw/1/")
    assert key.endswith(".mp4")

    # STS Token
    sts = FileService.generate_sts_token(key)
    assert "access_key_id" in sts
    assert "upload_url" in sts

    # 保存文件
    FileService.save_uploaded_file(key, b"test_data")
    assert os.path.exists(os.path.join(settings.LOCAL_UPLOAD_DIR, key))

    # HEAD Object
    head = FileService.head_object(key)
    assert head is not None
    assert head["content_length"] == 9

    # 公开 URL
    url = FileService.get_public_url(key)
    assert url.startswith("http")

    # 视频时长
    duration = FileService.get_video_duration(key)
    assert duration == 60  # mock 默认

    # 清理
    FileService.delete_object(key)
    assert not os.path.exists(os.path.join(settings.LOCAL_UPLOAD_DIR, key))


@pytest.mark.asyncio
async def test_file_service_validation():
    """FileService 文件验证"""
    assert FileService.validate_file_type("test.mp4") is True
    assert FileService.validate_file_type("test.mov") is True
    assert FileService.validate_file_type("test.avi") is False
    assert FileService.validate_file_type("test") is False

    assert FileService.validate_file_size(5 * 1024 * 1024) is True  # 5MB
    assert FileService.validate_file_size(500 * 1024 * 1024) is True  # 500MB
    assert FileService.validate_file_size(500 * 1024) is False  # 0.5MB too small
    assert FileService.validate_file_size(600 * 1024 * 1024) is False  # 600MB too large
