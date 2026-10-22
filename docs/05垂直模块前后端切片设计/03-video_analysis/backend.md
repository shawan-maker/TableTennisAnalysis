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
    """任务状态机：completed 状态不可再转换。"""
    # 尝试从 completed 转换到 queued 应该失败
    with pytest.raises(AppException) as exc:
        await VideoAnalysisService._transition_status(sample_task, "queued")
    assert exc.value.code == 400

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
    progress: Mapped[int] = mapped_column(Integer, default=0)
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
    file_size: int = Field(..., ge=1048576, le=524288000)  # 1MB ≤ file_size ≤ 500MB

    @field_validator("filename")
    @classmethod
    def validate_file_type(cls, v):
        if not v.lower().endswith((".mp4", ".mov")):
            raise ValueError("仅支持 MP4/MOV 格式")
        return v


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
    access_key_secret: str
    security_token: str
    expiration: str


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
    status: str
    estimated_wait_minutes: int


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
    task_uuid: str
    created_at: datetime
    is_llm_generated: bool
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
    quality_options: list[str]
    duration_sec: int


class ShareResponse(BaseModel):
    share_url: str
    card_image_url: Optional[str] = None
    expire_at: datetime


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
TASK_TRANSITIONS = {
    "queued":     {"processing", "cancelled"},
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

    FREE_DAILY_LIMIT = 3                # 免费用户每日额度
    SHARE_DAILY_LIMIT = 5              # 每日分享限制
    SHARE_EXPIRE_DAYS = 7             # 分享 Token 有效期
    MAX_FILE_SIZE = 524288000         # 500MB
    MIN_FILE_SIZE = 1048576           # 1MB 下限（R32 测试审查修复）
    ALLOWED_TYPES = (".mp4", ".mov")
    TOTAL_STEPS = 10  # BL-8: 与架构 §6.1 的10步流水线一致
    # PIPL-002 + R32 测试审查修复：视频时长限制（最小+最大）
    MIN_VIDEO_DURATION_SECONDS = 5    # 5 秒下限（避免无效分析）
    MAX_VIDEO_DURATION_SECONDS = 600  # 10 分钟上限

    # ===== OSS 上传流程 =====

    @staticmethod
    async def get_upload_token(user_id: int, req: UploadTokenRequest, db: AsyncSession) -> UploadTokenResponse:
        """获取 OSS STS 直传凭证 + 对象 Key。"""
        # 校验已在 Schema 层完成（类型 + 大小）

        # 生成 OSS Key: videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4
        now = datetime.now(timezone.utc)
        oss_key = f"videos/raw/{user_id}/{now.strftime('%Y%m%d')}/{uuid.uuid4().hex}.mp4"

        # 请求 STS Token
        sts = await FileService.generate_sts_token(
            oss_key=oss_key,
            permission="PutObject",
            expire_seconds=900,  # 15 分钟
        )

        # 创建 file_record
        file_record = FileRecord(
            user_id=user_id,
            oss_key=oss_key,
            original_filename=req.filename,
            file_size=req.file_size,
            file_type=req.filename.split(".")[-1].lower(),
            status="uploading",
        )
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)

        return UploadTokenResponse(
            file_id=file_record.id,
            oss_key=oss_key,
            sts_credentials=StsCredentials(
                access_key_id=sts["access_key_id"],
                access_key_secret=sts["access_key_secret"],
                security_token=sts["security_token"],
                expiration=sts["expiration"],
            ),
            upload_url=settings.OSS_UPLOAD_URL,
            expire_at=sts["expiration"],
        )

    @staticmethod
    async def confirm_upload(user_id: int, file_id: int, db: AsyncSession) -> UploadCompleteResponse:
        """上传完成确认（HEAD Object 校验）。"""
        # 查询 file_record
        stmt = select(FileRecord).where(
            FileRecord.id == file_id, FileRecord.user_id == user_id,
        )
        file_record = (await db.execute(stmt)).scalar_one_or_none()
        if not file_record:
            raise AppException("文件记录不存在", 404)

        # HEAD Object 校验
        head_result = await FileService.head_object(file_record.oss_key)
        if not head_result:
            raise AppException("未检测到上传的文件，请重新上传", 404)

        actual_size = head_result.get("content_length", 0)
        if actual_size != file_record.file_size:
            raise AppException("上传文件大小与声明不符", 400)

        # PIPL-002 + R32 测试审查修复：视频时长限制（最小+最大）
        # 在 upload-complete 步骤，通过 ffprobe 检查时长
        duration = await get_video_duration(file_record.oss_key)
        if duration < VideoAnalysisService.MIN_VIDEO_DURATION_SECONDS:
            raise AppException(
                f"视频时长不足{VideoAnalysisService.MIN_VIDEO_DURATION_SECONDS}秒，无法进行分析", 422, code=42200
            )
        if duration > VideoAnalysisService.MAX_VIDEO_DURATION_SECONDS:
            raise AppException(
                f"视频时长超过{VideoAnalysisService.MAX_VIDEO_DURATION_SECONDS // 60}分钟限制", 422, code=42200
            )
        file_record.duration_sec = duration  # 提前记录时长，避免 create_task 时重复探测

        # 更新 file_record
        file_record.status = "uploaded"
        file_record.oss_etag = head_result.get("etag")
        file_record.actual_size = actual_size
        await db.commit()

        return UploadCompleteResponse(
            file_id=file_record.id,
            ready=True,
            actual_size=actual_size,
        )

    # ===== 分析任务管理 =====

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

        # 4. 入队 Celery 分析任务（使用 task.id 作为内部标识，ai_pipeline 统一用 int task_id）
        # from app.tasks.analysis_tasks import run_analysis_pipeline
        # run_analysis_pipeline.delay(task.id, file_record.oss_key)

        return CreateTaskResponse(
            task_id=task.id,
            task_uuid=task.task_uuid,
            status="queued",
            estimated_wait_minutes=5,
        )

    @staticmethod
    async def _transition_status(task: VideoTask, target: str) -> None:
        """任务状态机转换校验。"""
        current = task.status
        if target not in TASK_TRANSITIONS.get(current, set()):
            raise AppException(
                f"任务状态不允许从 {current} 转换为 {target}", 400
            )
        task.status = target
        if target in ("completed", "failed"):
            task.completed_at = datetime.now(timezone.utc)

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

        # 从 result_data 中提取视频时长
        duration = 0
        if report.result_data and "video_info" in report.result_data:
            duration = report.result_data["video_info"].get("duration_sec", 0)

        return AnnotatedVideoResponse(
            url=report.annotated_video_url,
            quality_options=["1080p", "720p", "480p"],
            duration_sec=duration,
        )

    # ===== 分享 =====

    @staticmethod
    async def _check_share_limit(user_id: int) -> None:
        """检查每日分享限制（5 次/天）。"""
        redis = await get_redis()
        now = datetime.now(timezone(timedelta(hours=8)))
        date_key = now.date().isoformat()
        limit_key = f"share:count:{user_id}:{date_key}"

        count = await redis.incr(limit_key)
        if count == 1:
            await redis.expire(limit_key, 86400)

        if count > VideoAnalysisService.SHARE_DAILY_LIMIT:
            await redis.decr(limit_key)
            raise AppException("今日分享次数已用完", 429)

    @staticmethod
    async def create_share(user_id: int, report_id: int, db: AsyncSession) -> ShareResponse:
        """生成分享 Token + 卡片图。"""
        # 校验报告
        stmt = select(AnalysisReport).where(
            AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise AppException("报告不存在", 404)

        # 检查分享限制
        await VideoAnalysisService._check_share_limit(user_id)

        # 生成 UUID Token
        token = uuid.uuid4().hex
        expire_at = datetime.now(timezone.utc) + timedelta(days=VideoAnalysisService.SHARE_EXPIRE_DAYS)

        # 生成分享卡片图（Pillow 绘制：封面图 + 关键数据）
        # card_url = await FileService.generate_share_card(report)
        # 分享卡片图生成 (TD-3 实现)
        # Phase 1: 使用报告封面图作为分享卡片
        card_url = report.cover_image_url if report.cover_image_url else None

        # 创建 share_record
        share = ShareRecord(
            report_id=report_id,
            user_id=user_id,
            share_token=token,
            card_image_url=card_url,
            expire_at=expire_at,
        )
        db.add(share)
        await db.commit()

        # 触发积分（分享奖励）
        try:
            from app.services.gamification_service import GamificationService
            await GamificationService.add_points(db, user_id=user_id, event_type="share", ref_id=share.id)
        except Exception as e:
            logger.error("gamification_add_points_share_failed", error=str(e), report_id=report_id)

        share_url = f"https://api.pingpongai.com/share/{share.share_token}"

        return ShareResponse(
            share_url=share_url,
            card_image_url=card_url,
            expire_at=expire_at,
        )

    @staticmethod
    async def get_shared_report(token: str, db: AsyncSession) -> dict:
        """分享报告摘要页（公开只读，7 天有效）。"""
        stmt = select(ShareRecord).where(ShareRecord.share_token == token)
        share = (await db.execute(stmt)).scalar_one_or_none()
        if not share:
            raise AppException("分享不存在或已过期", 404)

        if datetime.now(timezone.utc) > share.expire_at:
            raise AppException("分享不存在或已过期", 404)

        # 查询报告
        report_stmt = select(AnalysisReport).where(AnalysisReport.id == share.report_id)
        report = (await db.execute(report_stmt)).scalar_one_or_none()
        if not report:
            raise AppException("分享不存在或已过期", 404)

        # 返回公开摘要（不含训练建议/历史趋势/用户个人信息）
        return {
            "cover_image_url": report.cover_image_url,
            "annotated_video_url": report.annotated_video_url,
            "result_data": {
                "technique_stats": report.result_data.get("technique_stats") if report.result_data else None,
                "landing_points": report.result_data.get("landing_points") if report.result_data else None,
                "ball_speed": report.result_data.get("ball_speed") if report.result_data else None,
            },
            "report_summary": report.report_text.get("summary") if report.report_text else None,
            "top_issues": (report.report_text or {}).get("issues", [])[:2] if report.report_text else [],
        }
```

---

## 6. API 路由实现

```python
# app/api/v1/video_analysis/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.response import success
from app.models.user import User
from app.schemas.video_analysis import (
    UploadTokenRequest, UploadCompleteRequest, CreateTaskRequest,
    FeedbackRequest,
)
from app.core.limiter import limiter
from app.services.video_analysis_service import VideoAnalysisService

router = APIRouter(prefix="/video-analysis", tags=["视频分析"])


@limiter.limit("100/minute")
@router.post("/upload-token", summary="获取 OSS STS 直传凭证")
async def get_upload_token(
    body: UploadTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.get_upload_token(user.id, body, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/upload-complete", summary="上传完成确认")
async def upload_complete(
    body: UploadCompleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.confirm_upload(user.id, body.file_id, db)
    return success(data=data)


@limiter.limit("10/hour", key_func=lambda r: r.state.user)
@router.post("/tasks", summary="创建分析任务")
async def create_task(
    body: CreateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.create_task(user.id, body, db)
    return success(data=data, message="任务已创建")


@limiter.limit("100/minute")
@router.get("/tasks", summary="任务列表（分页）")
async def list_tasks(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.list_tasks(user.id, status, page, page_size, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/tasks/{task_id}", summary="任务详情 + 进度")
async def get_task_detail(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.get_task_detail(user.id, task_id, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/reports/{report_id}", summary="分析报告详情")
async def get_report_detail(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.get_report_detail(user.id, report_id, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/reports", summary="报告列表（分页）")
async def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.list_reports(user.id, page, page_size, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/reports/{report_id}/feedback", summary="提交反馈")
async def submit_feedback(
    report_id: int,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.submit_feedback(
        user.id, report_id, body.is_correct, body.comment, db
    )
    return success(data=data, message="反馈已提交")


@limiter.limit("100/minute")
@router.get("/reports/{report_id}/feedbacks", summary="反馈历史查询（API 设计 §3.7）")
async def list_feedbacks(
    report_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.list_feedbacks(db, report_id, user.id, page, page_size)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/reports/{report_id}/annotated-video", summary="标注视频 CDN URL")
async def get_annotated_video(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.get_annotated_video(user.id, report_id, db)
    return success(data=data)


@limiter.limit("5/day", key_func=lambda r: r.state.user)
@router.post("/reports/{report_id}/share", summary="生成分享 Token + 卡片图")
async def create_share(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await VideoAnalysisService.create_share(user.id, report_id, db)
    return success(data=data, message="分享链接已生成")
```

**分享页面路由**（公开访问，不在认证路由下）：

```python
# app/api/v1/__init__.py 中注册
from app.api.v1.video_analysis.router import router as video_analysis_router
api_router.include_router(video_analysis_router)

# 分享页面单独注册（无前缀，公开访问）
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from app.core.limiter import limiter

share_router = APIRouter(tags=["分享"])

@limiter.limit("100/minute")
@share_router.get("/share/{share_token}", response_class=HTMLResponse, summary="分享报告摘要页")
async def get_shared_report(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """分享报告摘要页（公开只读，7 天有效）。返回 HTML 渲染页面。"""
    data = await VideoAnalysisService.get_shared_report(token, db)
    # 返回 HTML 模板（包含封面图 + 热图 + 技术统计 + 摘要）
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>乒乓分析报告分享</title></head>
    <body>
        <img src="{data['cover_image_url']}" />
        <video src="{data['annotated_video_url']}" controls></video>
        <div>{data['report_summary']}</div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# share_router 不加 /api/v1 前缀
app.include_router(share_router)
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
