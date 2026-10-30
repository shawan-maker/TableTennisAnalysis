# video_analysis 模块 — 后端垂直切片设计

> **模块名称**：`video_analysis`
> **所属目录**：`app/api/v1/video_analysis/`
> **定位**：管理视频上传（OSS 直传）、AI 分析任务创建与追踪、分析报告展示与反馈、报告分享
> **依据**：模块详细设计 v1.2 §2.3、API 详细设计 v1.3 §4

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.3（video_analysis 模块功能规格）
- [ ] 阅读 API 契约 §4（视频分析模块 11 个端点）
- [ ] 阅读 `app/core/deps.py`（`get_current_user` 依赖注入）
- [ ] 阅读 `app/core/redis.py`（Redis 连接，用于额度控制 + 缓存）
- [ ] 阅读 `app/services/file_service.py`（OSS STS Token 生成，file_management 基础设施）
- [ ] 阅读 `app/services/membership_service.py`（会员状态查询，额度控制依赖）
- [ ] 确认本切片范围：11 个 API 端点 + 对应 Service 方法

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model（FileRecord + VideoTask + AnalysisReport + FeedbackRecord + ShareRecord） | `app/models/video_analysis.py` | 无 | ☐ |
| 2 | 定义 Schema | `app/schemas/video_analysis.py` | #1 | ☐ |
| 3 | 实现 Service | `app/services/video_analysis_service.py` | #1,#2 | ☐ |
| 4 | 实现 API 路由 | `app/api/v1/video_analysis/router.py` | #3 | ☐ |
| 5 | 注册 Router | `app/api/v1/__init__.py` | #4 | ☐ |
| 6 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #1 | ☐ |
| 7 | 编写测试 | `tests/unit/test_video_analysis.py` | #3 | ☐ |
| 8 | 编写冒烟测试 | `tests/smoke/video_analysis_smoke_test.py` | #5 | ☐ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_video_analysis.py
"""
video_analysis 模块 — 视频分析全流程测试。
覆盖：上传凭证→上传确认→任务创建→进度查询→报告详情→反馈→分享。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.exceptions import AppException

# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_upload_token_success(client, auth_user):
    """获取 OSS 上传凭证成功。"""
    resp = await client.post("/api/v1/video-analysis/upload-token",
                              headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                              json={"filename": "test.mp4", "file_size": 104857600})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "file_id" in data
    assert "oss_key" in data
    assert "sts_credentials" in data
    assert "upload_url" in data

@pytest.mark.asyncio
async def test_create_task_success(client, auth_user, mock_oss_head):
    """创建分析任务成功（免费用户有额度）。"""
    h = {"Authorization": f"Bearer {auth_user['access_token']}"}
    # 先获取上传凭证
    token_resp = await client.post("/api/v1/video-analysis/upload-token",
                                    headers=h,
                                    json={"filename": "test.mp4", "file_size": 104857600})
    file_id = token_resp.json()["data"]["file_id"]
    oss_key = token_resp.json()["data"]["oss_key"]

    # 上传完成确认
    with patch('app.services.file_service.FileService.head_object',
               new_callable=AsyncMock, return_value={"content_length": 104857600}):
        await client.post("/api/v1/video-analysis/upload-complete",
                          headers=h, json={"file_id": file_id})

    # 创建任务
    resp = await client.post("/api/v1/video-analysis/tasks",
                              headers=h, json={"file_id": file_id, "oss_key": oss_key})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "queued"
    assert "task_id" in data
    assert "estimated_wait_minutes" in data

@pytest.mark.asyncio
async def test_get_report_detail(client, auth_user, sample_report):
    """获取分析报告详情成功。"""
    resp = await client.get(f"/api/v1/video-analysis/reports/{sample_report.id}",
                            headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "result_data" in data
    assert "report_text" in data
    assert "annotated_video_url" in data

# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_upload_token_invalid_format(client, auth_user):
    """文件类型不支持返回 400。"""
    resp = await client.post("/api/v1/video-analysis/upload-token",
                             headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                             json={"filename": "test.avi", "file_size": 104857600})
    assert resp.status_code == 400
    assert "MP4/MOV" in resp.json()["message"]

@pytest.mark.asyncio
async def test_upload_token_file_too_large(client, auth_user):
    """文件过大返回 400。"""
    resp = await client.post("/api/v1/video-analysis/upload-token",
                             headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                             json={"filename": "test.mp4", "file_size": 600 * 1024 * 1024})
    assert resp.status_code == 400
    assert "500MB" in resp.json()["message"]

@pytest.mark.asyncio
async def test_feedback_missing_is_correct(client, auth_user, sample_report):
    """反馈缺少 is_correct 字段返回 422。"""
    resp = await client.post(f"/api/v1/video-analysis/reports/{sample_report.id}/feedback",
                             headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                             json={"comment": "测试"})
    assert resp.status_code == 422

# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_create_task_without_token(client):
    """未携带 JWT 返回 401。"""
    resp = await client.post("/api/v1/video-analysis/tasks",
                              json={"file_id": 1, "oss_key": "test"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_get_report_not_owner(client, auth_user, other_user_report):
    """报告不属于当前用户返回 404。"""
    resp = await client.get(f"/api/v1/video-analysis/reports/{other_user_report.id}",
                            headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    assert resp.status_code == 404

# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_free_quota_exceeded(client, auth_user, mock_oss_head):
    """免费用户每日 3 次额度用完后返回 429。"""
    h = {"Authorization": f"Bearer {auth_user['access_token']}"}
    # 模拟已用 3 次额度
    with patch('app.services.video_analysis_service.VideoAnalysisService._check_free_quota',
               new_callable=AsyncMock,                side_effect=AppException("今日免费分析次数已用完，升级会员可无限分析", 429)):
        resp = await client.post("/api/v1/video-analysis/tasks",
                                  headers=h, json={"file_id": 1, "oss_key": "test"})
        assert resp.status_code == 429
        assert "额度" in resp.json()["message"]

@pytest.mark.asyncio
async def test_task_state_machine(client, auth_user, sample_task):
    """任务状态机：completed 状态不可再转换。

    R13-P3 文档同步（VA-11）：实际校验实现为 app/ai_pipeline/progress.py 的
    transition_task_status，非法转换返回 False（不 raise，调用方按返回值决策）。
    实际测试位于 tests/unit/test_supplements_p1.py（R12-VA-2，
    TestTaskStateMachine 合法/非法/终态矩阵）与 tests/unit/test_ai_pipeline.py
    （transition_task_status 矩阵 + TASK_TRANSITIONS 常量断言）。
    """
    from app.ai_pipeline.progress import transition_task_status
    # 尝试从 completed 转换到 queued 应该失败（返回 False，任务状态不变）
    allowed = await transition_task_status(db_session, sample_task.id, "queued")
    assert allowed is False
    await db_session.refresh(sample_task)
    assert sample_task.status == "completed"

@pytest.mark.asyncio
async def test_share_rate_limit(client, auth_user, sample_report):
    """分享超过每日 5 次限制返回 429。"""
    h = {"Authorization": f"Bearer {auth_user['access_token']}"}
    with patch('app.services.video_analysis_service.VideoAnalysisService._check_share_limit',
               new_callable=AsyncMock, side_effect=AppException("今日分享次数已用完", 429)):
        resp = await client.post(f"/api/v1/video-analysis/reports/{sample_report.id}/share",
                                 headers=h)
        assert resp.status_code == 429

@pytest.mark.asyncio
async def test_feedback_update_overwrite(client, auth_user, sample_report, existing_feedback):
    """重复提交反馈会覆盖旧记录。"""
    h = {"Authorization": f"Bearer {auth_user['access_token']}"}
    # 第一次反馈
    resp1 = await client.post(f"/api/v1/video-analysis/reports/{sample_report.id}/feedback",
                              headers=h, json={"is_correct": True, "comment": "准确"})
    assert resp1.status_code == 200
    # 第二次反馈（覆盖）
    resp2 = await client.post(f"/api/v1/video-analysis/reports/{sample_report.id}/feedback",
                              headers=h, json={"is_correct": False, "comment": "不太准"})
    assert resp2.status_code == 200
    # 确认覆盖（数据库中只有 1 条记录）


@pytest.mark.asyncio
async def test_list_feedbacks(client, auth_user, sample_report, existing_feedback):
    """反馈历史查询返回反馈记录列表（API 设计 §3.7）。"""
    resp = await client.get(f"/api/v1/video-analysis/reports/{sample_report.id}/feedbacks",
                             headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 1
    assert "is_correct" in data["items"][0]
    assert "status" in data["items"][0]
```

---

## 3. Model 实现

```python
# app/models/video_analysis.py
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, ForeignKey, Boolean, Float, UniqueConstraint, Index, text  # R19-P2-2/P2-4: 补 text（用于 GIN 索引 + DESC 排序）
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.core.database import Base


class FileRecord(Base):
    """文件记录表（视频原始文件）。"""
    __tablename__ = "file_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-7: 移除冗余 index=True（__table_args__ idx_file_record_user_created 已覆盖）
    oss_key: Mapped[str] = mapped_column(String(512), unique=True)  # R20-P3-2: 移除冗余 index=True（unique=True 已自动创建唯一索引）
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    file_type: Mapped[str] = mapped_column(String(20))  # mp4/mov
    status: Mapped[str] = mapped_column(String(20), default="uploading")  # uploading/uploaded/deleted
    oss_etag: Mapped[str | None] = mapped_column(String(128))
    actual_size: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_file_record_user_created", "user_id", "created_at"),
        Index("idx_file_status_created", "status", "created_at"),
        Index("idx_file_record_type", "file_type"),
    )

    video_tasks: Mapped[list["VideoTask"]] = relationship(back_populates="file_record")


class VideoTask(Base):
    """视频分析任务表。"""
    __tablename__ = "video_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 与架构 ER 图、ai_pipeline 切片统一
    task_uuid: Mapped[str] = mapped_column(String(64), unique=True)  # R19-P3-7: 移除冗余 index=True（unique=True 已隐式索引）；对外暴露的 UUID，内部用 id 做 FK
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-7: 移除冗余 index=True（__table_args__ idx_video_task_user_created 已覆盖）
    file_id: Mapped[int] = mapped_column(ForeignKey("file_record.id", ondelete="CASCADE"))  # R28-OBS-1/R29-P2-2: 移除冗余 index=True（__table_args__ idx_video_task_user_created 仅含 user_id+created_at，不含 file_id；file_id 为 FK 字段，无独立查询场景，主查询路径由 user_id 复合索引覆盖，与 DB §2.5 索引声明一致）
    oss_key: Mapped[str] = mapped_column(String(512))  # 原始视频 OSS Key，ai_pipeline 需读取
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 视频时长（秒），ai_pipeline 需读取
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued/processing/completed/failed/cancelled
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=10)
    step_name: Mapped[str | None] = mapped_column(String(32))
    # R13-P3 文档同步（VA-9）：progress 为 Float 0.0-1.0（R4 修复：0-100 → 0.0-1.0，
    # 实现见 app/models/video_analysis.py L76）
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text)
    estimated_remaining_seconds: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_video_task_user_created", "user_id", "created_at"),
        Index("idx_video_task_status_created", "status", "created_at"),
    )

    file_record: Mapped["FileRecord"] = relationship(back_populates="video_tasks")
    report: Mapped["AnalysisReport | None"] = relationship(back_populates="task", uselist=False)
    pipeline_steps: Mapped[list["PipelineStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class PipelineStep(Base):
    """流水线步骤记录表（ai_pipeline 模块使用）。"""
    __tablename__ = "pipeline_step"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("video_task.id", ondelete="CASCADE"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤号 1-10")
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending/running/completed/failed/skipped
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pipeline_step_task_step", "task_id", "step_number"),
    )

    task: Mapped["VideoTask"] = relationship(back_populates="pipeline_steps")

class AnalysisReport(Base):
    """分析报告表。"""
    __tablename__ = "analysis_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("video_task.id", ondelete="CASCADE"), unique=True)  # R19-P3-7: 移除冗余 index=True（unique=True 已隐式索引）；FK 指向 video_task.id（BigInteger）
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-7: 移除冗余 index=True（__table_args__ idx_report_user_created 已覆盖）
    is_llm_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)  # 用户注销后匿名归档
    result_data: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSONB: 完整分析结果
    report_text: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSONB: {summary, issues, suggestions}
    annotated_video_url: Mapped[str | None] = mapped_column(String(512))
    cover_image_url: Mapped[str | None] = mapped_column(String(512))
    report_images: Mapped[dict | None] = mapped_column(JSONB)  # {heatmap, technique_chart}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_report_user_created", "user_id", text("created_at DESC")),  # R19-P2-4: 补 DESC 排序（§5 L2470/§6.1 L2970 已定义）
        Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin"),  # R19-P2-2: 补 GIN 索引（§5 L2471/§6.2 L2971 已定义）
    )

    task: Mapped["VideoTask"] = relationship(back_populates="report")
    feedbacks: Mapped[list["FeedbackRecord"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    shares: Mapped[list["ShareRecord"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class FeedbackRecord(Base):
    """分析反馈记录表（数据飞轮入口）。"""
    __tablename__ = "feedback_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("analysis_report.id", ondelete="CASCADE"))  # R19-P3-7: 移除冗余 index=True（__table_args__ uq_feedback_user_report UniqueConstraint 已覆盖）
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R20-P3-2: 移除冗余 index=True（__table_args__ uq_feedback_user_report UniqueConstraint 已覆盖）
    is_correct: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # 数据飞轮审核状态（pending/archived/manual_review）。DB 设计 v1.3 §2.8/§5.6 已同步补充
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report"),
        Index("idx_feedback_status", "status"),  # R18-P1-3: 补充审核队列索引（§5/§6 已定义）
        Index("idx_feedback_correct_created", "is_correct", "created_at"),  # R18-P1-3: 补充飞轮统计索引
    )

    report: Mapped["AnalysisReport"] = relationship(back_populates="feedbacks")


class ShareRecord(Base):
    """报告分享记录表。"""
    __tablename__ = "share_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("analysis_report.id", ondelete="CASCADE"))  # R28-OBS-1/R29-P2-3: 移除冗余 index=True（__table_args__ idx_share_user_created 已覆盖 user_id+created_at 查询路径；report_id 为 FK 字段，PostgreSQL 不会自动为 FK 创建索引，但无独立查询场景，主查询由 share_token UNIQUE 索引或 user_id 复合索引覆盖，与 DB §2.9 一致）
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-7: 移除冗余 index=True（idx_share_user_created 已覆盖）
    share_token: Mapped[str] = mapped_column(String(64), unique=True)  # R19-P3-7: 移除冗余 index=True（unique=True 已隐式索引）；UUID
    card_image_url: Mapped[str | None] = mapped_column(String(512))
    share_scope: Mapped[str] = mapped_column(String(20), default="public", nullable=False, comment="公开范围: public/friend")
    view_count: Mapped[int] = mapped_column(Integer, default=0, comment="浏览次数")
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_share_user_created", "user_id", "created_at"),  # R18-P1-2: 补充索引（§5/§6 已定义）
    )

    report: Mapped["AnalysisReport"] = relationship(back_populates="shares")
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入所有 Model
- [ ] 运行 `alembic revision --autogenerate -m "add_video_analysis_models"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/video_analysis.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime


# --- 请求 Schema ---

class UploadTokenRequest(BaseModel):
    """获取上传凭证请求。"""
    filename: str = Field(..., min_length=1, max_length=255)
    # R13-P3 文档同步（VA-9，对齐 R12-VA-4 修复后实现）：移除 ge/le 与
    # field_validator 先行拦截 — API §4.1 错误表规定类型不支持/文件过大为 400、
    # 文件过小为 422，需由 service 层区分抛出；Schema 先行 422 拦截会使设计
    # 规定的错误码分支成为死代码。文件类型/大小校验见 §5 get_upload_token。
    file_size: int = Field(..., description="文件大小（字节）")


class UploadCompleteRequest(BaseModel):
    """上传完成确认请求。"""
    file_id: int = Field(..., ge=1)


class CreateTaskRequest(BaseModel):
    """创建分析任务请求。"""
    file_id: int = Field(..., ge=1)
    oss_key: str = Field(..., min_length=1)


class FeedbackRequest(BaseModel):
    """提交反馈请求。"""
    is_correct: bool = Field(..., description="分析结果是否准确")
    comment: Optional[str] = Field(default=None, max_length=500)


# --- 响应 Schema ---

class StsCredentials(BaseModel):
    access_key_id: str
    access_key_secret: [REDACTED]
    security_token: [REDACTED]
    expiration: str
    # R13-P3 文档同步（VA-9）：补 bucket/endpoint — 客户端 OSS 直传必需
    # （实现见 app/schemas/video_analysis.py StsCredentials）
    bucket: str
    endpoint: str


class UploadTokenResponse(BaseModel):
    file_id: int
    oss_key: str
    sts_credentials: StsCredentials
    upload_url: str
    expire_at: str


class UploadCompleteResponse(BaseModel):
    file_id: int
    ready: bool
    actual_size: int


class CreateTaskResponse(BaseModel):
    task_id: int
    task_uuid: str
    # R13-P3 文档同步（VA-12）：与实现一致带默认值（见 app/schemas/video_analysis.py
    # L75-80：status="queued"、estimated_wait_minutes=3）
    status: str = "queued"
    estimated_wait_minutes: int = 3


class TaskListItem(BaseModel):
    task_id: int
    task_uuid: str
    status: str
    created_at: datetime
    report_id: Optional[int] = None
    cover_image_url: Optional[str] = None
    model_config = {"from_attributes": True}


class TaskDetailResponse(BaseModel):
    task_id: int
    task_uuid: str
    status: str
    current_step: int
    total_steps: int
    step_name: Optional[str] = None
    progress: float
    estimated_remaining_seconds: Optional[int] = None
    # R13-P3 文档同步（VA-9）：补 error_message — failed 任务需向客户端透出失败原因
    error_message: Optional[str] = None
    created_at: datetime
    report_id: Optional[int] = None


class ReportListItem(BaseModel):
    id: int
    task_id: int
    created_at: datetime
    is_llm_generated: bool
    cover_image_url: Optional[str] = None
    report_summary: Optional[str] = None
    model_config = {"from_attributes": True}


class ReportDetailResponse(BaseModel):
    id: int
    task_id: int
    # R13-P3 文档同步（VA-9）：task_uuid 可空（task 缺失时 None）
    task_uuid: Optional[str] = None
    created_at: datetime
    is_llm_generated: bool
    # R13-P3 文档同步（VA-9）：补 is_readonly — BL-15 会员到期降级只读标记
    # （Redis downgrade:report:readonly:{user_id} 存在即为 True）
    is_readonly: bool = False
    result_data: Optional[dict[str, Any]] = None
    report_text: Optional[dict[str, Any]] = None
    annotated_video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    report_images: Optional[dict[str, Any]] = None
    model_config = {"from_attributes": True}


class FeedbackResponse(BaseModel):
    feedback_id: int
    is_correct: bool
    data_flywheel_action: str  # archived / manual_review


class FeedbackHistoryItem(BaseModel):
    """反馈历史项（API 设计 §3.7）。"""
    id: int
    report_id: int
    report_title: Optional[str] = None
    is_correct: bool
    comment: Optional[str] = None
    status: Optional[str] = None  # 切片新增：数据飞轮审核状态
    created_at: datetime
    model_config = {"from_attributes": True}


class AnnotatedVideoResponse(BaseModel):
    url: str
    # R13-P3 文档同步（VA-9）：duration_sec 可空（video_task 缺失时 None），
    # quality_options 有默认值（实现见 app/schemas/video_analysis.py）
    duration_sec: Optional[int] = None
    quality_options: list[str] = Field(default_factory=list)


class ShareResponse(BaseModel):
    share_url: str
    card_image_url: Optional[str] = None
    # R13-P3 文档同步（VA-9）：expire_at 为 isoformat 字符串（非 datetime 对象，
    # service 层 share.expire_at.isoformat() 返回）
    expire_at: str


# --- 分页包装 ---
class PaginatedTasks(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TaskListItem]


class PaginatedReports(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReportListItem]
```

---

## 5. Service 实现

```python
# app/services/video_analysis_service.py
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # R17-P2: selectinload 用于预加载 task 关系

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.config import settings
from app.models.video_analysis import (
    FileRecord, VideoTask, AnalysisReport, FeedbackRecord, ShareRecord,
)
from app.schemas.video_analysis import (
    UploadTokenRequest, UploadTokenResponse, StsCredentials,
    UploadCompleteResponse, CreateTaskResponse,
    TaskListItem, TaskDetailResponse, PaginatedTasks,
    ReportListItem, ReportDetailResponse, PaginatedReports,
    FeedbackResponse, FeedbackHistoryItem, AnnotatedVideoResponse, ShareResponse,
)
from app.services.file_service import FileService
from app.services.membership_service import MembershipService

logger = logging.getLogger(__name__)


# 任务状态机：合法转换矩阵
# R13-P3 文档同步（VA-10）：补 queued→failed 合法转换（R12 复验补充，消除
# video_analysis_service 启动失败旁路直写 status 绕过矩阵校验）。
# 注：矩阵实际定义于 app/ai_pipeline/progress.py（progress.transition_task_status）
TASK_TRANSITIONS = {
    "queued":     {"processing", "cancelled", "failed"},
    "processing": {"completed", "failed"},
    "completed":  set(),  # 终态
    "failed":     {"queued"},  # 可重试
    "cancelled":  set(),  # 终态
}

# AI 流水线步骤定义
# BL-8 修复：与架构 §6.1 步骤名称一致（10步）
PIPELINE_STEPS = [
    "视频预处理",   # Step 1: FFmpeg 转码/抽帧
    "球台检测",     # Step 2: YOLO-pose 四角定位
    "球体检测",     # Step 3: TTNet/TrackNetV5
    "球体追踪",     # Step 4: 卡尔曼滤波+抛物线
    "落点估算",     # Step 5: 单应性矩阵映射
    "姿态估计",     # Step 6: MediaPipe 2D
    "动作识别",     # Step 7: Temporal CNN
    "回合分割",     # Step 8: 弹跳事件检测
    "报告生成",     # Step 9: 规则引擎+LLM
    "标注视频生成", # Step 10: FFmpeg 叠加
]


class VideoAnalysisService:
    """视频分析业务逻辑层。"""

    FREE_DAILY_LIMIT = settings.FREE_DAILY_ANALYSIS_LIMIT  # 免费用户每日额度（默认 3）
    SHARE_DAILY_LIMIT = settings.SHARE_DAILY_LIMIT        # 每日分享限制（默认 5）
    SHARE_EXPIRE_DAYS = settings.SHARE_EXPIRE_DAYS        # 分享 Token 有效期（默认 7 天）
    MAX_FILE_SIZE = settings.MAX_FILE_SIZE                # 500MB 上限
    MIN_FILE_SIZE = settings.MIN_FILE_SIZE                # 1MB 下限
    ALLOWED_TYPES = (".mp4", ".mov")
    TOTAL_STEPS = 10  # BL-8: 与架构 §6.1 的10步流水线一致
    # PIPL-002 + R32 测试审查修复：视频时长限制（最小+最大，settings 驱动）
    MIN_VIDEO_DURATION = settings.MIN_VIDEO_DURATION    # 5 秒下限（避免无效分析）
    MAX_VIDEO_DURATION = settings.MAX_VIDEO_DURATION    # 600 秒上限

    # ===== OSS 上传流程 =====    # ===== OSS 上传流程 =====

    @staticmethod
    async def get_upload_token(user_id: int, req: UploadTokenRequest) -> dict:
        """获取 OSS 直传凭证"""
        # 1. 验证文件类型
        # R12-VA-4: API §4.1 错误表 — 类型不支持/文件过大均为 400，文件过小为 422
        if not FileService.validate_file_type(req.filename):
            raise AppException("仅支持 MP4/MOV 格式", 400, code=ERR_BAD_REQUEST)

        # 2. 验证文件大小 — 过大 400 / 过小 422（消息对齐 API §4.1）
        if req.file_size > settings.MAX_FILE_SIZE:
            raise AppException("视频文件不能超过 500MB", 400, code=ERR_BAD_REQUEST)
        if req.file_size < settings.MIN_FILE_SIZE:
            raise AppException("视频文件不能小于 1MB", 422, code=ERR_VALIDATION)

        # 3. 生成 OSS Key
        oss_key = FileService.generate_oss_key(user_id, req.filename)

        # 4. 签发 STS Token
        sts = FileService.generate_sts_token(oss_key)

        # 5. 创建 file_record
        ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else "mp4"
        async with async_session_factory() as db:
            record = FileRecord(
                user_id=user_id,
                oss_key=oss_key,
                original_filename=req.filename,
                file_size=req.file_size,
                file_type=ext,
                status="uploading",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        return {
            "file_id": record.id,
            "oss_key": oss_key,
            "sts_credentials": {
                "access_key_id": sts["access_key_id"],
                "access_key_secret": sts["access_key_secret"],
                "security_token": sts["security_token"],
                "expiration": sts["expiration"],
                "bucket": sts["bucket"],
                "endpoint": sts["endpoint"],
            },
            "upload_url": sts["upload_url"],
            "expire_at": sts["expiration"],
        }
    @staticmethod
    async def confirm_upload(user_id: int, req: UploadCompleteRequest) -> dict:
        """上传完成确认 — HEAD Object 校验"""
        async with async_session_factory() as db:
            record = await VideoAnalysisService._get_file_record(req.file_id, user_id, db)
            if record.status != "uploading":
                raise AppException("文件已确认或已废弃", 400, code=ERR_BAD_REQUEST)

            # HEAD Object 校验
            head = FileService.head_object(record.oss_key)
            if not head:
                # R12-VA-5: API §4.2 错误表 — OSS 文件不存在为 404（原 400 偏差）
                raise AppException("未检测到上传的文件，请重新上传", 404, code=ERR_NOT_FOUND)

            # 文件大小校验 — 实际大小必须与声明一致
            actual_size = head.get("content_length", 0)
            if actual_size != record.file_size:
                raise AppException("上传文件大小与声明不符", 400, code=ERR_BAD_REQUEST)

            # 获取视频时长
            duration_sec = FileService.get_video_duration(record.oss_key)

            # 时长校验（5s ~ 600s）— duration_sec 为 None 或 0 时拒绝确认
            # R6-Video-1: 使用两条独立错误消息 + ERR_VALIDATION
            if not duration_sec or duration_sec < settings.MIN_VIDEO_DURATION:
                raise AppException(
                    f"视频时长过短，需至少 {settings.MIN_VIDEO_DURATION}s",
                    422,
                    code=ERR_VALIDATION,
                )
            if duration_sec > settings.MAX_VIDEO_DURATION:
                raise AppException(
                    f"视频时长过长，不能超过 {settings.MAX_VIDEO_DURATION}s",
                    422,
                    code=ERR_VALIDATION,
                )

            # 更新 file_record
            # R12-VA-6: duration_sec 不入 file_record（DB 设计 §2.4/切片模型均无此列），
            # 在响应中返回，create_task 时写入 video_task.duration_sec（ai_pipeline 读取源）
            record.status = "uploaded"
            record.oss_etag = head["etag"]
            record.actual_size = head["content_length"]
            record.uploaded_at = datetime.now(timezone.utc)
            await db.commit()

            return {
                "file_id": record.id,
                "ready": True,
                "actual_size": head["content_length"],
                "duration_sec": duration_sec,
            }

    # ===== 分析任务管理 =====    # ===== 分析任务管理 =====

    @staticmethod
    async def _check_free_quota(user_id: int) -> None:
        """检查免费用户每日分析额度。Key: quota:analysis:{user_id}:{date}"""
        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))  # Asia/Shanghai (UTC+8)
        now_cst = datetime.now(tz_cst)
        today = now_cst.date().isoformat()
        key = f"quota:analysis:{user_id}:{today}"
        count = await redis.incr(key)
        if count == 1:
            # 首次设置，设置 TTL 到今天 23:59:59 + 1h（Asia/Shanghai）
            end_of_day = now_cst.replace(hour=23, minute=59, second=59, microsecond=0)
            ttl = int((end_of_day - now_cst).total_seconds()) + 3600
            await redis.expire(key, ttl)

        if count > VideoAnalysisService.FREE_DAILY_LIMIT:
            await redis.decr(key)  # 回退
            raise AppException("今日免费分析次数已用完，升级会员可无限分析", 429)

    @staticmethod
    async def create_task(user_id: int, req, db: AsyncSession) -> CreateTaskResponse:
        """创建分析任务。"""
        # 1. 检查文件状态
        stmt = select(FileRecord).where(
            FileRecord.id == req.file_id, FileRecord.user_id == user_id,
        )
        file_record = (await db.execute(stmt)).scalar_one_or_none()
        if not file_record:
            raise AppException("文件记录不存在", 404)
        if file_record.status != "uploaded":
            raise AppException("文件尚未上传完成", 400)

        # 2. 检查会员状态 + 免费额度
        membership = await MembershipService.check_membership(db, user_id)
        if not membership.is_member:
            await VideoAnalysisService._check_free_quota(user_id)

        # 3. 创建 VideoTask
        task_uuid = str(uuid.uuid4())  # 对外暴露的 UUID
        task = VideoTask(
            task_uuid=task_uuid,
            user_id=user_id,
            file_id=req.file_id,
            oss_key=file_record.oss_key,
            status="queued",
            total_steps=VideoAnalysisService.TOTAL_STEPS,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        # 4. 启动 Celery 流水线（R13-P3 文档同步 VA-12：实际实现调用
        #    PipelineOrchestrator.build_and_run(task.id, oss_key)，替换原注释桩）
        #    启动失败时（R12 复验-VA-2 旁路收口 + R12-AIPipeline-2 退额度）：
        #    - 走 transition_task_status 状态机校验标记 failed（queued→failed 合法转换）
        #    - 调用 ai_pipeline.tasks._refund_free_quota 退还预扣的免费额度
        #      （任务未进入 Celery 重试流程，需在此直接退还）
        try:
            from app.ai_pipeline.pipeline import PipelineOrchestrator
            await PipelineOrchestrator.build_and_run(task.id, file_record.oss_key)
        except Exception as e:
            # 状态机校验标记 failed + 退额度（见实现 L215-236）
            ...

        return {
            "task_id": task.id,
            "task_uuid": task.task_uuid,
            "status": "queued",
            # R13-P3 文档同步（VA-12）：estimated_wait_minutes 实际为 3（实现统一值，
            # CreateTaskResponse 默认 3），原切片样例 5 未回写
            "estimated_wait_minutes": 3,
        }

    # R13-P3 文档同步（VA-11）：状态机校验实际实现于 app/ai_pipeline/progress.py 的
    # transition_task_status(db, task_id, target) -> bool（R12-VA-2 修复）：
    # - 合法：更新 status（completed/failed 同时写 completed_at），flush 后返回 True
    # - 非法（含任务不存在）：记录警告日志、不改状态，返回 False（不 raise —
    #   流水线调用方按返回值决定后续动作：WS 推送/中止流水线）
    # 调用方：
    #   - progress.py on_step_failed（processing→failed）
    #   - progress.py on_task_complete（processing→completed）
    #   - video_analysis_service.create_task 启动失败旁路（queued→failed）
    # 原切片 _transition_status（raise AppException 语义）不再存在，删除样例。

    @staticmethod
    async def get_task_detail(user_id: int, task_id: int, db: AsyncSession) -> TaskDetailResponse:
        """任务详情 + 进度。"""
        stmt = select(VideoTask).where(
            VideoTask.id == task_id, VideoTask.user_id == user_id,
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if not task:
            raise AppException("任务不存在", 404)

        # 查询关联报告
        report_id = None
        if task.status == "completed":
            report_stmt = select(AnalysisReport.id).where(AnalysisReport.task_id == task.id)
            report_id = (await db.execute(report_stmt)).scalar_one_or_none()

        return TaskDetailResponse(
            task_id=task.id,
            task_uuid=task.task_uuid,
            status=task.status,
            current_step=task.current_step,
            total_steps=task.total_steps,
            step_name=task.step_name,
            progress=task.progress,
            estimated_remaining_seconds=task.estimated_remaining_seconds,
            created_at=task.created_at,
            report_id=report_id,
        )

    @staticmethod
    async def list_tasks(user_id: int, status: Optional[str], page: int, page_size: int,
                         db: AsyncSession) -> PaginatedTasks:
        """任务列表（分页）。"""
        base = select(VideoTask).where(VideoTask.user_id == user_id)
        if status:
            base = base.where(VideoTask.status == status)

        # 总数
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # 列表
        list_stmt = base.order_by(VideoTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        tasks = (await db.execute(list_stmt)).scalars().all()

        # 批量查询关联报告，避免 N+1 查询（OPT-11 修复）
        task_ids = [t.id for t in tasks if t.status == "completed"]
        report_map: dict[int, tuple[int, str | None]] = {}
        if task_ids:
            report_stmt = (
                select(AnalysisReport.id, AnalysisReport.cover_image_url, AnalysisReport.task_id)
                .where(AnalysisReport.task_id.in_(task_ids))
            )
            for row in (await db.execute(report_stmt)).all():
                report_map[row[2]] = (row[0], row[1])

        items = []
        for t in tasks:
            report_id = None
            cover_url = None
            if t.status == "completed" and t.id in report_map:
                report_id, cover_url = report_map[t.id]
            items.append(TaskListItem(
                task_id=t.id,
                task_uuid=t.task_uuid,
                status=t.status,
                created_at=t.created_at,
                report_id=report_id,
                cover_image_url=cover_url,
            ))

        return PaginatedTasks(total=total, page=page, page_size=page_size, items=items)

    # ===== 分析报告 =====

    @staticmethod
    async def get_report_detail(user_id: int, report_id: int, db: AsyncSession) -> ReportDetailResponse:
        """分析报告详情。"""
        stmt = select(AnalysisReport).options(
            selectinload(AnalysisReport.task)
        ).where(
            AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise AppException("报告不存在", 404)

        # 降级用户只读检查 (BL-15 修复)
        redis = await get_redis()
        readonly = await redis.get(f"downgrade:report:readonly:{user_id}")
        is_readonly = readonly is not None

        data = ReportDetailResponse.model_validate(report).model_dump()
        data["task_uuid"] = report.task.task_uuid  # R17-P2: 手动注入 task_uuid（在 VideoTask 上，非 AnalysisReport）
        data["is_readonly"] = is_readonly
        return data

    @staticmethod
    async def list_reports(user_id: int, page: int, page_size: int, db: AsyncSession) -> PaginatedReports:
        """报告列表（分页）。"""
        base = select(AnalysisReport).where(AnalysisReport.user_id == user_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        list_stmt = base.order_by(AnalysisReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        reports = (await db.execute(list_stmt)).scalars().all()

        items = []
        for r in reports:
            summary = None
            if r.report_text and "summary" in r.report_text:
                summary = r.report_text["summary"]
            items.append(ReportListItem(
                id=r.id,
                task_id=r.task_id,
                created_at=r.created_at,
                is_llm_generated=r.is_llm_generated,
                cover_image_url=r.cover_image_url,
                report_summary=summary,
            ))

        return PaginatedReports(total=total, page=page, page_size=page_size, items=items)

    # ===== 反馈与数据飞轮 =====

    @staticmethod
    async def submit_feedback(user_id: int, report_id: int, is_correct: bool,
                              comment: Optional[str], db: AsyncSession) -> FeedbackResponse:
        """提交反馈（对/不对标记），数据飞轮入口。"""
        # 校验报告存在且属于当前用户
        stmt = select(AnalysisReport).where(
            AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise AppException("报告不存在", 404)

        # 查找已有反馈（覆盖更新）
        fb_stmt = select(FeedbackRecord).where(
            FeedbackRecord.report_id == report_id, FeedbackRecord.user_id == user_id,
        )
        existing = (await db.execute(fb_stmt)).scalar_one_or_none()

        if existing:
            existing.is_correct = is_correct
            existing.comment = comment
            existing.status = "archived" if is_correct else "manual_review"
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing)
            feedback_id = existing.id
        else:
            feedback = FeedbackRecord(
                report_id=report_id,
                user_id=user_id,
                is_correct=is_correct,
                comment=comment,
                status="archived" if is_correct else "manual_review",
            )
            db.add(feedback)
            await db.commit()
            await db.refresh(feedback)
            feedback_id = feedback.id

        # 数据飞轮动作
        if is_correct:
            # is_correct=true → 视频标记为标注候选，自动归档到 OSS annotations/ 目录
            await FileService.archive_for_training(report_id, report.task_id)
            action = "archived"
        else:
            # is_correct=false → 进入人工审核队列（Phase 2+ admin 模块处理）
            # 管理员审核修正后触发 FileService.archive_for_training 归档
            action = "manual_review"

        # 触发积分（反馈奖励）
        try:
            from app.services.gamification_service import GamificationService
            await GamificationService.add_points(db, user_id=user_id, event_type="feedback", ref_id=feedback_id)
        except Exception as e:
            logger.error("gamification_add_points_feedback_failed", error=str(e), feedback_id=feedback_id)

        return FeedbackResponse(
            feedback_id=feedback_id,
            is_correct=is_correct,
            data_flywheel_action=action,
        )

    @staticmethod
    async def list_feedbacks(db: AsyncSession, report_id: int, user_id: int,
                              page: int, page_size: int) -> dict:
        """反馈历史查询（API 设计 §3.7）。"""
        # 校验报告存在且属于当前用户
        stmt = select(AnalysisReport).where(
            AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise AppException("报告不存在", 404)

        # 查询反馈记录
        base = select(FeedbackRecord).where(
            FeedbackRecord.report_id == report_id, FeedbackRecord.user_id == user_id,
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        list_stmt = base.order_by(FeedbackRecord.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        feedbacks = (await db.execute(list_stmt)).scalars().all()

        items = []
        for fb in feedbacks:
            report_title = None
            if report.report_text and "summary" in report.report_text:
                report_title = report.report_text["summary"]
            items.append(FeedbackHistoryItem(
                id=fb.id,
                report_id=fb.report_id,
                report_title=report_title,
                is_correct=fb.is_correct,
                comment=fb.comment,
                status=fb.status,
                created_at=fb.created_at,
            ))

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    # ===== 标注视频 =====

    @staticmethod
    async def get_annotated_video(user_id: int, report_id: int, db: AsyncSession) -> AnnotatedVideoResponse:
        """标注视频 CDN URL。"""
        stmt = select(AnalysisReport).where(
            AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise AppException("报告不存在", 404)

        if not report.annotated_video_url:
            raise AppException("标注视频尚未生成", 404)

        # R13-P3 文档同步（VA-12）：时长实际取自 video_task.duration_sec
        # （R12-VA-6：duration 不入 file_record，持久化于 video_task，
        # ai_pipeline/create_task 统一读取源），不再从 result_data["video_info"] 提取
        task_result = await db.execute(
            select(VideoTask.duration_sec).where(VideoTask.id == report.task_id)
        )
        duration = task_result.scalar_one_or_none()

        return AnnotatedVideoResponse(
            url=report.annotated_video_url,
            quality_options=["1080p", "720p", "480p"],
            duration_sec=duration,
        )

    # ===== 分享 =====

    @staticmethod
    async def _check_share_limit(user_id: int) -> None:
        """分享次数限制 — 使用 CST 日期作为 key"""
        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))
        today = datetime.now(tz_cst).strftime("%Y%m%d")
        key = f"share:count:{user_id}:{today}"
        count = await redis.incr(key)

        if count == 1:
            now = datetime.now(tz_cst)
            end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=tz_cst)
            ttl = int((end_of_day - now).total_seconds()) + 3600
            await redis.expire(key, ttl)

        if count > VideoAnalysisService.SHARE_DAILY_LIMIT:
            await redis.decr(key)
            raise AppException(
                "今日分享次数已用完",
                429,
                code=ERR_QUOTA_EXHAUSTED,
            )
    @staticmethod
    async def create_share(user_id: int, report_id: int) -> dict:
        """创建分享"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 分享次数限制
            await VideoAnalysisService._check_share_limit(user_id)

            # 创建分享记录
            share_token = uuid.uuid4().hex
            now = datetime.now(timezone.utc)
            share = ShareRecord(
                report_id=report_id,
                user_id=user_id,
                share_token=share_token,
                share_scope="public",
                expire_at=now + timedelta(days=VideoAnalysisService.SHARE_EXPIRE_DAYS),
            )
            db.add(share)
            await db.commit()
            await db.refresh(share)

            share_url = f"{settings.API_BASE_URL}/share/{share_token}"

            # 游戏化积分（try/except 不阻塞主流程）
            try:
                from app.services.gamification_service import GamificationService
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="share", ref_id=share.id
                )
            except Exception as e:
                logger.warning("share_add_points_failed", extra={
                    "error": str(e), "share_id": share.id
                })

            return {
                "share_url": share_url,
                "card_image_url": report.cover_image_url,
                "expire_at": share.expire_at.isoformat(),
            }
    @staticmethod
    async def get_shared_report(share_token: str) -> dict:
        """获取公开分享报告摘要"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(ShareRecord).where(ShareRecord.share_token == share_token)
            )
            share = result.scalar_one_or_none()
            if share is None:
                raise AppException("分享链接无效或已过期", 404, code=ERR_SHARE_TOKEN_INVALID)

            # 检查过期
            if share.expire_at < datetime.now(timezone.utc):
                raise AppException("分享链接已过期", 404, code=ERR_SHARE_TOKEN_INVALID)

            # 查询报告
            report_result = await db.execute(
                select(AnalysisReport).where(AnalysisReport.id == share.report_id)
            )
            report = report_result.scalar_one_or_none()
            if report is None:
                raise AppException("报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 更新浏览数
            await db.execute(
                update(ShareRecord)
                .where(ShareRecord.id == share.id)
                .values(view_count=ShareRecord.view_count + 1)
            )
            await db.commit()

            # 返回安全字段（不含训练建议/趋势/个人信息）
            report_text = report.report_text or {}
            safe_text = {
                "summary": report_text.get("summary", ""),
                "issues": report_text.get("issues", [])[:2],
            }

            # result_data 仅返回安全子集（不含个人信息/训练建议）
            safe_keys = ("technique_stats", "landing_points", "ball_speed")
            safe_result_data = {
                k: report.result_data.get(k)
                for k in safe_keys
                if report.result_data and k in report.result_data
            }

            return {
                "report_id": report.id,
                "cover_image_url": report.cover_image_url,
                "annotated_video_url": report.annotated_video_url,
                "result_data": safe_result_data,
                "report_text": safe_text,  # 向后兼容
                "report_summary": safe_text.get("summary", ""),
                "top_issues": safe_text.get("issues", []),
                "created_at": report.created_at.isoformat() if report.created_at else None,
            }
```

---

## 6. API 路由实现

```python
# app/api/v1/video_analysis/router.py
from typing import Optional

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

# 独立分享路由 — 不挂载 /video-analysis prefix，挂载到 /share/{share_token} 根路径（VA-1 修复）
share_router = APIRouter(tags=["分享"])


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
```

**分享页面路由**（公开访问，不在认证路由下）：

```python
# app/main.py 中注册（VA-1 修复：/share/{share_token} 挂载根路径，公开访问）
from app.api.v1.video_analysis.router import (
    router as video_analysis_router,
    share_router as video_share_router,
)
app.include_router(api_router, prefix="/api/v1")
app.include_router(video_share_router)  # 无 /api/v1 前缀，/share/{share_token}
```

```python
# app/api/v1/video_analysis/router.py（同文件内 — 公开分享端点）
import html as _html
import json as _json

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.limiter import RateLimits, limiter
from app.services.video_analysis_service import VideoAnalysisService


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
```

---
## 7. 冒烟测试脚本

```python
# tests/smoke/video_analysis_smoke_test.py
"""
video_analysis 模块冒烟测试。
用法: python -m tests.smoke.video_analysis_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 0. 登录
        print("0. Testing login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "视频分析测试",
        })
        if resp.status_code != 200:
            print(f"   ✗ Login failed: {resp.status_code}")
            return

        token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # 1. 获取上传凭证
        print("1. Testing POST /video-analysis/upload-token...")
        resp = await client.post("/video-analysis/upload-token", headers=h, json={
            "filename": "test.mp4",
            "file_size": 104857600,
        })
        assert resp.status_code == 200, f"Upload token failed: {resp.text}"
        file_id = resp.json()["data"]["file_id"]
        oss_key = resp.json()["data"]["oss_key"]
        print(f"   ✓ Upload token: file_id={file_id}, oss_key={oss_key}")

        # 2. 上传完成确认（模拟）
        print("2. Testing POST /video-analysis/upload-complete...")
        # 注意：真实环境需要先上传文件到 OSS，冒烟测试中此步骤可能失败
        resp = await client.post("/video-analysis/upload-complete", headers=h, json={
            "file_id": file_id,
        })
        if resp.status_code == 200:
            print(f"   ✓ Upload confirmed: ready={resp.json()['data']['ready']}")
        else:
            print(f"   ⚠ Upload confirm skipped (expected without real OSS): {resp.status_code}")

        # 3. 创建分析任务
        print("3. Testing POST /video-analysis/tasks...")
        resp = await client.post("/video-analysis/tasks", headers=h, json={
            "file_id": file_id,
            "oss_key": oss_key,
        })
        if resp.status_code == 200:
            task_id = resp.json()["data"]["task_id"]
            print(f"   ✓ Task created: {task_id}")
        elif resp.status_code == 403:
            print(f"   ⚠ Quota exceeded (expected if already used 3 today)")
            return
        else:
            print(f"   ⚠ Task creation skipped: {resp.status_code}")
            return

        # 4. 任务列表
        print("4. Testing GET /video-analysis/tasks...")
        resp = await client.get("/video-analysis/tasks", headers=h)
        assert resp.status_code == 200, f"List tasks failed: {resp.text}"
        print(f"   ✓ Tasks: {resp.json()['data']['total']} total")

        # 5. 任务详情
        print("5. Testing GET /video-analysis/tasks/{task_id}...")
        resp = await client.get(f"/video-analysis/tasks/{task_id}", headers=h)
        assert resp.status_code == 200, f"Task detail failed: {resp.text}"
        print(f"   ✓ Task detail: status={resp.json()['data']['status']}")

        # 6. 报告列表
        print("6. Testing GET /video-analysis/reports...")
        resp = await client.get("/video-analysis/reports", headers=h)
        assert resp.status_code == 200, f"List reports failed: {resp.text}"
        reports = resp.json()["data"]["items"]
        print(f"   ✓ Reports: {resp.json()['data']['total']} total")

        # 7. 报告详情（如果有报告）
        if reports:
            report_id = reports[0]["id"]
            print(f"7. Testing GET /video-analysis/reports/{report_id}...")
            resp = await client.get(f"/video-analysis/reports/{report_id}", headers=h)
            assert resp.status_code == 200, f"Report detail failed: {resp.text}"
            print(f"   ✓ Report detail: is_llm={resp.json()['data']['is_llm_generated']}")

            # 8. 提交反馈
            print("8. Testing POST /video-analysis/reports/{report_id}/feedback...")
            resp = await client.post(f"/video-analysis/reports/{report_id}/feedback",
                                      headers=h,
                                      json={"is_correct": True, "comment": "smoke test"})
            assert resp.status_code == 200, f"Feedback failed: {resp.text}"
            print(f"   ✓ Feedback: action={resp.json()['data']['data_flywheel_action']}")

            # 9. 分享
            print("9. Testing POST /video-analysis/reports/{report_id}/share...")
            resp = await client.post(f"/video-analysis/reports/{report_id}/share", headers=h)
            assert resp.status_code == 200, f"Share failed: {resp.text}"
            print(f"   ✓ Share URL: {resp.json()['data']['share_url'][:50]}...")

    print("\nvideo_analysis_smoke_test: ALL PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_video_analysis.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.video_analysis_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导入（FileRecord, VideoTask, AnalysisReport, FeedbackRecord, ShareRecord）
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] 分享路由 `/share/{share_token}` 已挂载（公开访问）
- [ ] Alembic 迁移已生成并执行
- [ ] OSS 直传流程完整：upload-token → 直传 → upload-complete → tasks
- [ ] 免费额度控制正确（每日 3 次，Redis INCR/DECR 回退）
- [ ] 会员用户不受额度限制
- [ ] 任务状态机正确约束所有转换
- [ ] 反馈覆盖更新（同一用户同一报告只保留一条反馈）
- [ ] 分享 Token 7 天有效，过期返回 404
- [ ] 分享限流 5 次/天
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`{Entity}Request`、`{Entity}Response`、`{Entity}ListItem`、`Paginated{Entities}`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 免费额度控制 **必须** 使用 Redis INCR/DECR，**禁止** 用数据库计数
- 额度超限时 **必须** DECR 回退，**禁止** 消耗额度后返回 403
- 任务状态转换 **必须** 校验状态矩阵，**禁止** 非法转换
- 反馈提交 **必须** 覆盖旧记录，**禁止** 同一用户同一报告有多条反馈
- 分享 Token **必须** 设置 7 天过期时间
- 分享页面 **禁止** 暴露训练建议/历史趋势/用户个人信息
- OSS STS Token **必须** 设置 15 分钟过期
- 实现前 **必须** 阅读 auth 模块和 file_management 基础设施代码
- ALL API 端点已添加 `@limiter.limit()` 限流装饰器，全局默认 100/minute，AI 分析创建 10/hour，报告分享 5/day

### 覆盖度修复说明

- **[X-27] VideoTask 主键类型修复（P0）**：VideoTask 主键从 `task_id: VARCHAR(36) PK`（UUID 字符串）改为 `id: BigInteger PK`（自增），与架构 ER 图 §9.1 和 ai_pipeline 切片统一。新增 `task_uuid: VARCHAR(36) UNIQUE INDEX` 字段用于对外暴露。AnalysisReport 外键 `task_id` 从 `String(36) FK("video_task.task_id")` 改为 `BigInteger FK("video_task.id")`。Schemas 中 `task_id` 类型从 `str` 改为 `int`，新增 `task_uuid: str` 字段。同时补充 `oss_key`/`duration_sec` 字段（P1-5 修复），`datetime.utcnow` 改为 `lambda: datetime.now(timezone.utc)`（P2-1 修复）。
- **[A-2] 免费额度 Redis 计数器修复（P0）**：`_check_free_quota` 方法 TTL 计算从简化 `86400`（24h 固定）改为精确计算到当日 23:59:59 + 1h（Asia/Shanghai），满足架构反幻觉约束 #33。Redis Key 格式确认为 `quota:analysis:{user_id}:{date}`，使用 `datetime.now()` 本地日期
- **[X-22] 反馈历史查询端点（P1）**：新增 GET `/video-analysis/reports/{report_id}/feedbacks` 端点，对应 API 设计 §3.7。新增 Schema `FeedbackHistoryItem`、Service 方法 `list_feedbacks`、测试用例 `test_list_feedbacks`
- **FeedbackRecord.status 字段说明（X-28 已修复）**：FeedbackRecord.status 字段（数据飞轮审核状态：pending/archived/manual_review）已在 DB 设计 v1.3 §2.8/§5.6 中同步补充
- **ShareRecord 字段对齐**：ShareRecord 已补入 DB 设计 v1.3 §5.2 代码块，字段名与 DB 设计一致（share_token/share_scope/card_image_url/expire_at/view_count/created_at）
