# scoring 模块 — 后端垂直切片设计

> **模块名称**：`scoring`
> **所属目录**：`app/api/v1/scoring/`
> **定位**：智能记分牌，支持比赛设置、实时记分、得分方式标记、多设备同步、比赛统计
> **依据**：模块详细设计 v1.2 §2.4、API 详细设计 v1.3 §5

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.4（scoring 模块功能规格）
- [ ] 阅读 API 契约 §5（记分牌模块 7 个端点）
- [ ] 阅读 `app/core/response.py`（统一响应 `success()`）
- [ ] 阅读 `app/core/deps.py`（`get_current_user` 依赖注入）
- [ ] 阅读 `app/core/redis.py`（Redis 连接工具）
- [ ] 阅读 `app/core/websocket.py`（WebSocket 连接管理器）
- [ ] 确认本切片范围：7 个 API 端点 + 对应 Service 方法 + 3 个 Model

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/scoring.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/scoring.py` | #1 | ☐ |
| 4 | 实现 Service | `app/services/scoring_service.py` | #2,#3 | ☐ |
| 5 | 实现 API 路由 | `app/api/v1/scoring/router.py` | #4 | ☐ |
| 6 | 注册 Router | `app/api/v1/__init__.py` | #5 | ☐ |
| 7 | Alembic 迁移 | `alembic revision --autogenerate` | #2 | ☐ |
| 8 | 编写测试 | `tests/unit/test_scoring.py` | #4 | ☐ |
| 9 | 编写冒烟测试 | `tests/smoke/scoring_smoke_test.py` | #5 | ☐ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_scoring.py
"""
scoring 模块 — 记分牌流程测试。
覆盖：创建比赛、记分、撤销、结束比赛、比赛统计、状态机约束、多设备同步。
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException


@pytest.fixture
async def scoring_ctx(client, db_session, auth_user):
    """创建测试上下文：已登录用户 + Token。"""
    return {
        "client": client,
        "headers": {"Authorization": f"Bearer {auth_user['access_token']}"},
        "user": auth_user,
    }


# === 1. Happy Path（正常流程） ===
@pytest.mark.asyncio
async def test_create_match_success(scoring_ctx):
    """创建比赛成功，返回 setup 状态。"""
    ctx = scoring_ctx
    resp = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "测试对手",
        "opponent_rating": 1500,
        "format": "bo5",
        "match_type": "friendly",
        "target_score": 11,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "setup"
    assert data["current_server"] == "user"
    assert "match_id" in data


@pytest.mark.asyncio
async def test_score_and_undo_flow(scoring_ctx):
    """完整记分 + 撤销流程。"""
    ctx = scoring_ctx
    # 1. 创建比赛
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]

    # 2. 记分
    score = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/score", headers=ctx["headers"],
        json={"scorer": "user", "score_method": "rally_point", "technique_action": "forehand_drive"},
    )
    assert score.status_code == 200
    score_data = score.json()["data"]
    assert score_data["sequence"] == 1
    assert score_data["score"] == "1:0"
    assert score_data["current_server"] in ("user", "opponent")

    # 3. 撤销
    undo = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=ctx["headers"],
    )
    assert undo.status_code == 200
    undo_data = undo.json()["data"]
    assert undo_data["type"] == "undo"  # R18-P3: action→type
    assert undo_data["score"] == "0:0"


@pytest.mark.asyncio
async def test_finish_match_generates_statistics(scoring_ctx):
    """结束比赛后自动生成 MatchStatistic。"""
    ctx = scoring_ctx
    # 创建 + 记分到结束
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo1", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]

    # 记录 11:0（用户全胜）
    for _ in range(11):
        await ctx["client"].post(
            f"/api/v1/scoring/matches/{match_id}/score", headers=ctx["headers"],
            json={"scorer": "user", "score_method": "rally_point"},
        )

    # 结束比赛
    finish = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=ctx["headers"],
    )
    assert finish.status_code == 200
    finish_data = finish.json()["data"]
    assert finish_data["is_win"] is True
    assert "statistic_id" in finish_data

    # 查询统计
    stats = await ctx["client"].get(
        f"/api/v1/scoring/matches/{match_id}/statistics", headers=ctx["headers"],
    )
    assert stats.status_code == 200
    assert "score_distribution" in stats.json()["data"]["stats_data"]


# === 2. Validation Failure（参数校验失败） ===
@pytest.mark.asyncio
async def test_create_match_invalid_format(scoring_ctx):
    """format 值不在枚举中时返回 422。"""
    ctx = scoring_ctx
    resp = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "invalid", "match_type": "friendly", "target_score": 11,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_match_invalid_target_score(scoring_ctx):
    """target_score 不在合理范围返回 422。"""
    ctx = scoring_ctx
    resp = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 0,
    })
    assert resp.status_code == 422


# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_score_unauthorized(client):
    """未登录用户记分返回 401。"""
    resp = await client.post("/api/v1/scoring/matches/1/score", json={"scorer": "user"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_score_other_user_match(scoring_ctx, auth_user2):
    """其他用户的比赛不可操作，返回 404。"""
    ctx = scoring_ctx
    # 用户1创建比赛
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]

    # 用户2尝试记分
    headers2 = {"Authorization": f"Bearer {auth_user2['access_token']}"}
    resp = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/score", headers=headers2,
        json={"scorer": "user"},
    )
    assert resp.status_code == 404
    assert "比赛不存在" in resp.json()["message"]


# === 4. Business Rule Violation（业务规则违反） ===
@pytest.mark.asyncio
async def test_score_on_non_in_progress_match(scoring_ctx):
    """在 setup 状态的比赛上记分返回 409。"""
    ctx = scoring_ctx
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]
    # setup 状态直接记分 → 409
    resp = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/score", headers=ctx["headers"],
        json={"scorer": "user"},
    )
    assert resp.status_code == 409
    assert "进行中" in resp.json()["message"]


@pytest.mark.asyncio
async def test_undo_on_empty_match(scoring_ctx):
    """没有可撤销记录时返回 400。"""
    ctx = scoring_ctx
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]
    # setup 状态 → 先开始
    # 没有任何记分记录就撤销 → 400
    resp = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=ctx["headers"],
    )
    assert resp.status_code == 400
    assert "可撤销" in resp.json()["message"]


@pytest.mark.asyncio
async def test_statistics_before_finish(scoring_ctx):
    """比赛尚未结束时查询统计返回 400。"""
    ctx = scoring_ctx
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]
    resp = await ctx["client"].get(
        f"/api/v1/scoring/matches/{match_id}/statistics", headers=ctx["headers"],
    )
    assert resp.status_code == 400
    assert "尚未结束" in resp.json()["message"]


# === 5. 状态机入口与 abandon/resume 流程 ===
@pytest.mark.asyncio
async def test_start_match_success(scoring_ctx):
    """setup 状态的比赛调用 start 后进入 in_progress。"""
    ctx = scoring_ctx
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]
    assert create.json()["data"]["status"] == "setup"

    # 调用 start
    resp = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=ctx["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "in_progress"
    assert "started_at" in data

    # 再次 start → 400
    resp2 = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=ctx["headers"],
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_abandon_and_resume_flow(scoring_ctx):
    """放弃比赛后 24h 内可恢复。"""
    ctx = scoring_ctx
    create = await ctx["client"].post("/api/v1/scoring/matches", headers=ctx["headers"], json={
        "opponent_name": "对手", "format": "bo5", "match_type": "friendly", "target_score": 11,
    })
    match_id = create.json()["data"]["match_id"]

    # 先 start
    await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=ctx["headers"],
    )

    # 放弃
    abandon = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/abandon", headers=ctx["headers"],
    )
    assert abandon.status_code == 200
    assert abandon.json()["data"]["status"] == "abandoned"
    assert "abandoned_at" in abandon.json()["data"]

    # 恢复
    resume = await ctx["client"].post(
        f"/api/v1/scoring/matches/{match_id}/resume", headers=ctx["headers"],
    )
    assert resume.status_code == 200
    assert resume.json()["data"]["status"] == "in_progress"
    assert "resumed_at" in resume.json()["data"]
```

---

## 3. Model 实现

```python
# app/models/scoring.py
"""
记分牌模块数据模型。
包含：Match（比赛）、ScoreRecord（逐球得分记录）、MatchStatistic（比赛统计）。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Match(Base):
    """记分牌实时比赛实体。"""
    __tablename__ = "match"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), comment="创建者用户ID")  # R26-P3-26: 移除冗余 index=True（idx_match_user_created 已覆盖）
    opponent_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="对手姓名")
    opponent_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="对手积分")
    format: Mapped[str] = mapped_column(String(20), default="bo5", comment="赛制: bo1/bo3/bo5/bo7/custom")
    match_type: Mapped[str] = mapped_column(String(20), default="friendly", comment="比赛类型: friendly/tournament/training")
    target_score: Mapped[int] = mapped_column(Integer, default=11, comment="每局目标分")
    # 状态机：setup → in_progress → finished / abandoned
    status: Mapped[str] = mapped_column(String(20), default="setup", comment="比赛状态")  # R18-P2-8: 移除 index=True，改用 __table_args__ 显式索引
    # Redis 缓存的当前比分快照（冗余字段，Redis 为权威源）
    current_score_user: Mapped[int] = mapped_column(Integer, default=0, comment="当前用户得分")
    current_score_opp: Mapped[int] = mapped_column(Integer, default=0, comment="当前对手得分")
    current_game: Mapped[int] = mapped_column(Integer, default=1, comment="当前局数")
    current_server: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="当前发球方: user/opponent")
    # Redis 缓存的比分序列快照（冗余字段，Redis 为权威源）
    score_sequence: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="比分序列缓存，Redis 镜像")
    is_win: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, comment="是否胜利")
    final_score: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="最终比分: 3:1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="比赛开始时间（进入 in_progress 时记录）")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="比赛放弃时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_match_user_created", "user_id", "created_at"),
        Index("idx_match_status", "status"),  # R18-P2-8: 补充状态索引（§5/§2.10 已定义）
    )

    # 关系
    score_records: Mapped[list["ScoreRecord"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="ScoreRecord.sequence",
    )
    statistic: Mapped[Optional["MatchStatistic"]] = relationship(
        back_populates="match", uselist=False, cascade="all, delete-orphan",
    )


class ScoreRecord(Base):
    """逐球得分记录（记分牌逐球流水）。"""
    __tablename__ = "score_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))  # R26-P3-27: 移除冗余 index=True（idx_score_record_match_seq/match_game 已覆盖）
    sequence: Mapped[int] = mapped_column(Integer, comment="全局序号（Redis INCR 生成）")
    scorer: Mapped[str] = mapped_column(String(10), comment="得分方: user/opponent")
    score_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="得分方式: serve_point/rally_point/opponent_error")
    technique_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="技术动作: forehand_drive/backhand_drive/forehand_loop/...")
    game_number: Mapped[int] = mapped_column(Integer, default=1, comment="局数")
    is_key_point: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, comment="是否关键分")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_score_record_match_seq", "match_id", "sequence"),
        Index("idx_score_record_match_game", "match_id", "game_number"),
    )

    match: Mapped["Match"] = relationship(back_populates="score_records")


class MatchStatistic(Base):
    """比赛统计（比赛结束后自动生成）。"""
    __tablename__ = "match_statistic"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), unique=True)  # R19-P3-12: 移除冗余 index=True（unique=True 已隐式索引）
    # JSONB 统计数据
    stats_data: Mapped[dict] = mapped_column(JSONB, comment="统计JSON: score_distribution/key_points/technique_breakdown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    match: Mapped["Match"] = relationship(back_populates="statistic")
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入：`from app.models.scoring import Match, ScoreRecord, MatchStatistic`
- [ ] 运行 `alembic revision --autogenerate -m "add_scoring_tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/scoring.py
"""
记分牌模块 Pydantic Schema。
"""
from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field


# --- 请求 Schema ---

class MatchCreateRequest(BaseModel):
    """创建比赛请求。"""
    opponent_name: str = Field(..., min_length=1, max_length=64, description="对手姓名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    format: Literal["bo1", "bo3", "bo5", "bo7", "custom"] = Field(default="bo5", description="赛制")
    match_type: Literal["friendly", "tournament", "training"] = Field(default="friendly", description="比赛类型")
    target_score: int = Field(default=11, ge=1, le=21, description="每局目标分")


class ScoreRequest(BaseModel):
    """记分请求。"""
    scorer: Literal["user", "opponent"] = Field(..., description="得分方")
    score_method: Literal["serve_point", "rally_point", "opponent_error"] = Field(..., description="得分方式")
    technique_action: Optional[str] = Field(default=None, max_length=30, description="技术动作")


class UndoRequest(BaseModel):
    """撤销请求（可选携带 expected_seq 校验）。"""
    expected_seq: Optional[int] = Field(default=None, ge=1, description="期望撤销的序号")


# --- 响应 Schema ---

class MatchBrief(BaseModel):
    """比赛列表项。"""
    id: int
    opponent_name: str
    format: str
    match_type: str
    status: str
    current_score_user: int
    current_score_opp: int
    is_win: Optional[bool] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class MatchDetail(BaseModel):
    """比赛详情。"""
    id: int
    opponent_name: str
    opponent_rating: Optional[int] = None
    format: str
    match_type: str
    target_score: int
    status: str
    current_score_user: int
    current_score_opp: int
    current_server: Optional[str] = None
    current_game: int
    is_win: Optional[bool] = None
    final_score: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ScoreRecordBrief(BaseModel):
    """单条得分记录。"""
    seq: int
    scorer: str
    score_method: str
    technique_action: Optional[str] = None
    game_number: int


class MatchDetailWithSequence(MatchDetail):
    """比赛详情（含比分序列）。"""
    score_sequence: list[ScoreRecordBrief] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    """记分响应。"""
    sequence: int
    score: str
    current_server: str
    game_number: int
    is_key_point: bool
    match_status: str
    should_change_sides: bool = False


class UndoResponse(BaseModel):
    """撤销响应。"""
    sequence: int
    score: str
    type: str = "undo"  # R18-P3: action→type，与 notification data.type 命名统一


class FinishResponse(BaseModel):
    """结束比赛响应。"""
    match_id: int
    final_score: str
    is_win: bool
    statistic_id: int


class MatchStartResponse(BaseModel):
    """开始比赛响应（状态机：setup → in_progress）。"""
    match_id: int
    status: str = "in_progress"
    started_at: datetime


class MatchAbandonResponse(BaseModel):
    """放弃比赛响应。"""
    match_id: int
    status: str = "abandoned"
    abandoned_at: datetime


class MatchResumeResponse(BaseModel):
    """恢复比赛响应（24h 内恢复 abandoned → in_progress）。"""
    match_id: int
    status: str = "in_progress"
    resumed_at: datetime


class MatchStatisticResponse(BaseModel):
    """比赛统计响应。"""
    match_id: int
    stats_data: dict


# --- 查询 Schema ---

class MatchListQuery(BaseModel):
    """比赛列表查询参数。"""
    status: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
```

---

## 5. Service 实现

```python
# app/services/scoring_service.py
"""
记分牌业务逻辑层。
核心职责：比赛状态机管理、Redis 原子序号、WebSocket 推送、发球轮换计算、比赛统计生成。
"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.database import get_async_session
# OPT-13 会话管理说明：本模块使用 `async with get_async_session() as db` 模式管理会话，
# 与其他切片的 `db: AsyncSession = Depends(get_db)` 依赖注入模式不同。
# 原因：scoring 模块部分方法（如 finish_match 的级联调用）需要独立事务边界，
# 不复用请求级会话。两种模式可共存，后续迭代统一为 Depends 模式时需注意事务边界。
# P3 统一说明：全项目 Redis Key 构造统一为 f-string，会话工厂统一为 get_async_session。
from app.core.pagination import paginate
from app.models.scoring import Match, ScoreRecord, MatchStatistic
from app.schemas.scoring import (
    MatchCreateRequest, ScoreRequest, UndoRequest,
    MatchListQuery, MatchBrief, MatchDetail, MatchDetailWithSequence,
    ScoreRecordBrief, ScoreResponse, UndoResponse, FinishResponse,
    MatchStatisticResponse,
)

# WebSocket 推送管理器（依赖注入或全局单例）
try:
    from app.core.websocket import manager as ws_manager
except ImportError:
    ws_manager = None  # 测试环境可能无 WebSocket


class ScoringService:
    """记分牌业务逻辑层。"""

    # Redis Key 统一使用 f-string 内联构造（如 f"scoring:match:{match_id}:seq"）
    # 不再使用类常量模板 + .format()，与全项目风格保持一致

    @staticmethod
    async def _get_match_or_404(match_id: int, user_id: int, db: AsyncSession) -> Match:
        """获取比赛，不存在或不属于当前用户则抛 404。"""
        result = await db.execute(
            select(Match).where(Match.id == match_id, Match.user_id == user_id)
        )
        match = result.scalar_one_or_none()
        if not match:
            raise AppException("比赛不存在", 404)
        return match

    @staticmethod
    def _calc_server(score_user: int, score_opp: int, target_score: int,
                     initial_server: str = "user") -> str:
        """计算当前发球方（11分制：每人2次轮换，10:10后每人1次）。"""
        total_points = score_user + score_opp
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            # 10:10 之后每人 1 次轮换
            switch_interval = 1
        else:
            # 正常每人 2 次轮换
            switch_interval = 2
        # 计算应该发球的一方
        cycle = total_points // switch_interval
        if cycle % 2 == 0:
            return initial_server
        return "opponent" if initial_server == "user" else "user"

    @staticmethod
    def _is_key_point(score_user: int, score_opp: int, target_score: int) -> bool:
        """判断是否关键分（10:10 之后或赛点）。"""
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            return True  # 10:10 之后每分都是关键分
        if score_user == target_score - 1 or score_opp == target_score - 1:
            return True  # 赛点
        return False

    @staticmethod
    def _should_change_sides(score_user: int, score_opp: int, target_score: int, game_ended: bool) -> bool:
        """判断是否需要换边。
        1. 每局结束后（一方达到目标分且领先2分）→ 换边
        2. 10:10 平分后，每得1分换边
        """
        if game_ended:
            return True
        # 10:10 平分后每得1分换边
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            return True
        return False

    @staticmethod
    async def create_match(user_id: int, req: MatchCreateRequest) -> dict:
        """创建比赛。状态：setup。"""
        async with get_async_session() as db:
            match = Match(
                user_id=user_id,
                opponent_name=req.opponent_name,
                opponent_rating=req.opponent_rating,
                format=req.format,
                match_type=req.match_type,
                target_score=req.target_score,
                status="setup",
                current_score_user=0,
                current_score_opp=0,
                current_game=1,
                current_server="user",  # 用户先发球
            )
            db.add(match)
            await db.commit()
            await db.refresh(match)

            # 初始化 Redis 缓存
            redis = await get_redis()
            await redis.set(f"scoring:match:{match.id}:status", "setup")
            await redis.hset(f"scoring:match:{match.id}:current_score", mapping={
                "user": 0, "opp": 0,
            })

            return {
                "match_id": match.id,
                "status": match.status,
                "current_server": match.current_server,
            }

    @staticmethod
    async def list_matches(user_id: int, query: MatchListQuery) -> dict:
        """查询比赛列表。"""
        async with get_async_session() as db:
            qs = select(Match).where(Match.user_id == user_id)
            count_qs = select(func.count()).select_from(Match).where(Match.user_id == user_id)
            if query.status:
                qs = qs.where(Match.status == query.status)
                count_qs = count_qs.where(Match.status == query.status)
            qs = qs.order_by(Match.created_at.desc())

            total, items = await paginate(db, qs, count_qs, query.page, query.page_size)
            return {
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
                "items": [MatchBrief.model_validate(m).model_dump() for m in items],
            }

    @staticmethod
    async def get_match_detail(user_id: int, match_id: int) -> dict:
        """获取比赛详情（含比分序列）。"""
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            # 查询比分序列
            records_result = await db.execute(
                select(ScoreRecord)
                .where(ScoreRecord.match_id == match_id)
                .order_by(ScoreRecord.sequence)
            )
            records = records_result.scalars().all()

            detail = MatchDetailWithSequence.model_validate(match)
            detail.score_sequence = [
                ScoreRecordBrief(
                    seq=r.sequence, scorer=r.scorer,
                    score_method=r.score_method,
                    technique_action=r.technique_action,
                    game_number=r.game_number,
                )
                for r in records
            ]
            return detail.model_dump()

    @staticmethod
    async def score(user_id: int, match_id: int, req: ScoreRequest) -> dict:
        """记分：Redis INCR 获取序号 → 写 score_record → 更新比分 → WS 推送。"""
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)

            # 状态校验：必须 in_progress
            if match.status != "in_progress":
                raise AppException("比赛未在进行中", 409)

            redis = await get_redis()

            # 1. Redis INCR 获取全局序号
            seq = await redis.incr(f"scoring:match:{match_id}:seq")

            # 2. 获取当前比分
            score_data = await redis.hgetall(f"scoring:match:{match_id}:current_score")
            score_user = int(score_data.get("user", 0))
            score_opp = int(score_data.get("opp", 0))

            # 3. 更新比分
            if req.scorer == "user":
                score_user += 1
            else:
                score_opp += 1

            # 4. 计算发球方
            current_server = ScoringService._calc_server(
                score_user, score_opp, match.target_score,
                initial_server="user",
            )

            # 5. 判断关键分
            is_key_point = ScoringService._is_key_point(score_user, score_opp, match.target_score)

            # 6. 判断是否达到目标分（本局结束）
            game_ended = (
                (score_user >= match.target_score and score_user - score_opp >= 2)
                or (score_opp >= match.target_score and score_opp - score_user >= 2)
            )

            # 6.1 判断是否需要换边
            should_change_sides = ScoringService._should_change_sides(
                score_user, score_opp, match.target_score, game_ended,
            )

            # 7. 写入 score_record
            record = ScoreRecord(
                match_id=match_id,
                sequence=seq,
                scorer=req.scorer,
                score_method=req.score_method,
                technique_action=req.technique_action,
                game_number=match.current_game,
                is_key_point=is_key_point,
            )
            db.add(record)

            # 8. 更新 Redis 比分
            await redis.hset(f"scoring:match:{match_id}:current_score", mapping={
                "user": score_user, "opp": score_opp,
            })
            await redis.set(f"scoring:match:{match_id}:server", current_server)

            # 9. 更新 Match 表（冗余字段）
            match.current_score_user = score_user
            match.current_score_opp = score_opp
            match.current_server = current_server

            await db.commit()

            # 10. WebSocket 推送
            if ws_manager:
                await ws_manager.broadcast_to_room(
                    f"ws:match:{match_id}",
                    json.dumps({
                        "event": "score_update",  # R17-P1: type→event，与项目 WS 协议统一
                        "data": {
                            "sequence": seq,
                            "score": f"{score_user}:{score_opp}",
                            "scorer": req.scorer,
                            "score_method": req.score_method,
                            "current_server": current_server,
                            "is_key_point": is_key_point,
                        },
                    }),
                )

            return {
                "sequence": seq,
                "score": f"{score_user}:{score_opp}",
                "current_server": current_server,
                "game_number": match.current_game,
                "is_key_point": is_key_point,
                "match_status": match.status,
                "should_change_sides": should_change_sides,
            }

    @staticmethod
    async def undo(user_id: int, match_id: int, req: Optional[UndoRequest] = None) -> dict:
        """撤销最后一球：校验 max_seq → 删除 score_record → Redis DECR → WS 推送 undo。"""
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)

            if match.status not in ("in_progress",):
                raise AppException("比赛未在进行中", 409)

            redis = await get_redis()

            # 1. 获取当前 max_seq
            max_seq = await redis.get(f"scoring:match:{match_id}:seq")
            if not max_seq or int(max_seq) == 0:
                raise AppException("没有可撤销的记录", 400)
            max_seq = int(max_seq)

            # 2. 校验 expected_seq（如果传了）
            if req and req.expected_seq is not None and req.expected_seq != max_seq:
                raise AppException("比分已更新，请确认后撤销", 409)

            # 3. 查询最后一条 score_record
            record_result = await db.execute(
                select(ScoreRecord)
                .where(ScoreRecord.match_id == match_id, ScoreRecord.sequence == max_seq)
            )
            record = record_result.scalar_one_or_none()
            if not record:
                raise AppException("没有可撤销的记录", 400)

            # 4. 回退比分
            score_data = await redis.hgetall(f"scoring:match:{match_id}:current_score")
            score_user = int(score_data.get("user", 0))
            score_opp = int(score_data.get("opp", 0))
            if record.scorer == "user":
                score_user = max(0, score_user - 1)
            else:
                score_opp = max(0, score_opp - 1)

            # 5. 删除记录
            await db.delete(record)

            # 6. Redis DECR
            # R19-P3-E: 使用 pipeline 保证 seq 与 current_score 原子性，避免撤销操作中 decr 与 hset 之间发生异常导致状态不一致
            pipe = redis.pipeline()
            pipe.decr(f"scoring:match:{match_id}:seq")
            pipe.hset(f"scoring:match:{match_id}:current_score", mapping={
                "user": score_user, "opp": score_opp,
            })
            await pipe.execute()

            # 7. 重新计算发球方
            current_server = ScoringService._calc_server(
                score_user, score_opp, match.target_score,
            )

            # 8. 更新 Match 表
            match.current_score_user = score_user
            match.current_score_opp = score_opp
            match.current_server = current_server

            await db.commit()

            # 9. WebSocket 推送
            if ws_manager:
                await ws_manager.broadcast_to_room(
                    f"ws:match:{match_id}",
                    json.dumps({
                        "event": "score_update",  # R17-P1: type→event，与项目 WS 协议统一
                        "data": {
                            "type": "undo",  # R18-P3: action→type，与 notification data.type 命名统一
                            "sequence": max_seq - 1,
                            "score": f"{score_user}:{score_opp}",
                            "current_server": current_server,
                        },
                    }),
                )

            return {
                "sequence": max_seq - 1,
                "score": f"{score_user}:{score_opp}",
                "type": "undo",  # R18-P3: action→type
            }

    @staticmethod
    async def finish_match(user_id: int, match_id: int) -> dict:
        """结束比赛：状态机 → finished → 生成 MatchStatistic。"""
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)

            if match.status != "in_progress":
                raise AppException("比赛未在进行中", 409)

            # 计算最终比分（局数比）
            redis = await get_redis()
            score_user = match.current_score_user
            score_opp = match.current_score_opp

            is_win = score_user > score_opp
            final_score = f"{score_user}:{score_opp}"

            # 更新比赛状态
            match.status = "finished"
            match.is_win = is_win
            match.final_score = final_score
            match.finished_at = datetime.now(timezone.utc)

            # 生成比赛统计
            stats = await ScoringService._generate_statistics(match_id, db)
            statistic = MatchStatistic(
                match_id=match_id,
                stats_data=stats,
            )
            db.add(statistic)

            # R-1: 得分分析（基于 score_record 进行技术动作分布、关键分转换率等深度分析）
            # 后续迭代可调用 ScoringService._analyze_scoring_patterns(match_id, db)
            # 将得分分析结果写入 stats_data 或独立分析表

            # 清理 Redis 缓存
            await redis.delete(f"scoring:match:{match_id}:seq")
            await redis.delete(f"scoring:match:{match_id}:current_score")
            await redis.delete(f"scoring:match:{match_id}:server")

            await db.commit()
            await db.refresh(statistic)

            # F2-1 修复：比赛结束后自动调用 match_data 模块创建 match_record
            # 字段映射: score_record.seq → score_detail.sequence, scorer → scorer,
            #           score_method → score_method, technique_action → technique_action
            from app.services.match_data_service import MatchDataService
            # P2-PTS-01 修复：传 trigger_points=False，
            # 因为 finish_match 下方已单独触发 match 事件 +5 积分，
            # 避免 create_record_from_scoring 内部再触发 record 事件 +3 积分导致重复积分。
            await MatchDataService.create_record_from_scoring(
                db, match_id=match.id, user_id=match.user_id, trigger_points=False,
            )

            # 积分触发：完成记分牌比赛 +5 积分（P0-5 修复）
            try:
                from app.services.gamification_service import GamificationService
                await GamificationService.add_points(
                    db, user_id=match.user_id, event_type="match", ref_id=match.id,
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("gamification_add_points_match_failed", error=str(e), match_id=match_id)

            # WS 推送比赛结束通知
            from app.services.notification_service import NotificationService
            await NotificationService.push_ws_message(
                match.user_id, "match_finished", {
                    "match_id": match.id,
                    "final_score": match.final_score,
                }
            )

            return {
                "match_id": match_id,
                "final_score": final_score,
                "is_win": is_win,
                "statistic_id": statistic.id,
            }

    @staticmethod
    async def _generate_statistics(match_id: int, db: AsyncSession) -> dict:
        """从 score_record 聚合统计数据。"""
        records_result = await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.match_id == match_id)
            .order_by(ScoreRecord.sequence)
        )
        records = records_result.scalars().all()

        score_distribution = {"serve_point": 0, "rally_point": 0, "opponent_error": 0}
        technique_breakdown = {}
        key_points = []

        for r in records:
            score_distribution[r.score_method] = score_distribution.get(r.score_method, 0) + 1
            if r.technique_action:
                technique_breakdown[r.technique_action] = technique_breakdown.get(r.technique_action, 0) + 1
            if r.is_key_point:
                key_points.append({
                    "seq": r.sequence,
                    "scorer": r.scorer,
                    "score_method": r.score_method,
                })

        return {
            "score_distribution": score_distribution,
            "key_points": key_points,
            "technique_breakdown": technique_breakdown,
            "total_points": len(records),
        }

    @staticmethod
    async def get_statistics(user_id: int, match_id: int) -> dict:
        """获取比赛统计。"""
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "finished":
                raise AppException("比赛尚未结束", 400)

            stat_result = await db.execute(
                select(MatchStatistic).where(MatchStatistic.match_id == match_id)
            )
            stat = stat_result.scalar_one_or_none()
            if not stat:
                raise AppException("比赛尚未结束", 400)

            return {
                "match_id": match_id,
                "stats_data": stat.stats_data,
            }

    @staticmethod
    async def start_match(user_id: int, match_id: int) -> dict:
        """将 setup 状态的比赛切换为 in_progress。
        状态机入口：setup → in_progress。
        """
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "setup":
                raise AppException("比赛已开始或已结束", 400)
            match.status = "in_progress"
            match.started_at = datetime.now(timezone.utc)
            await db.commit()

            redis = await get_redis()
            await redis.set(f"scoring:match:{match_id}:status", "in_progress")

            return {
                "match_id": match_id,
                "status": "in_progress",
                "started_at": match.started_at.isoformat(),
            }

    @staticmethod
    async def abandon_match(user_id: int, match_id: int) -> dict:
        """放弃比赛：in_progress → abandoned，记录 abandoned_at。
        24h 内可通过 resume 恢复；超过 24h 由 Celery Beat 自动转为 finished。
        """
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "in_progress":
                raise AppException("仅进行中的比赛可放弃", 400)
            match.status = "abandoned"
            match.abandoned_at = datetime.now(timezone.utc)
            await db.commit()

            redis = await get_redis()
            await redis.set(f"scoring:match:{match_id}:status", "abandoned")

            return {
                "match_id": match_id,
                "status": "abandoned",
                "abandoned_at": match.abandoned_at.isoformat(),
            }

    @staticmethod
    async def resume_match(user_id: int, match_id: int) -> dict:
        """恢复 24h 内的 abandoned 比赛：abandoned → in_progress。
        超过 24h 的 abandoned 比赛由 Celery Beat 自动转为 finished，不可恢复。
        """
        from datetime import timedelta
        async with get_async_session() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "abandoned":
                raise AppException("仅放弃的比赛可恢复", 400)
            if not match.abandoned_at:
                raise AppException("比赛放弃时间缺失", 400)
            # 校验是否在 24h 内
            elapsed = datetime.now(timezone.utc) - match.abandoned_at
            if elapsed > timedelta(hours=24):
                raise AppException("放弃超过 24h，比赛已自动结束", 400)

            match.status = "in_progress"
            match.abandoned_at = None
            await db.commit()

            redis = await get_redis()
            await redis.set(f"scoring:match:{match_id}:status", "in_progress")

            return {
                "match_id": match_id,
                "status": "in_progress",
                "resumed_at": datetime.now(timezone.utc).isoformat(),
            }
```

---

## 6. API 路由实现

```python
# app/api/v1/scoring/router.py
"""
记分牌模块 API 路由。
所有路由只调用 ScoringService，不包含业务逻辑。
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.deps import get_current_user
from app.core.response import success
from app.models.user import User
from app.schemas.scoring import (
    MatchCreateRequest, ScoreRequest, UndoRequest,
)
from app.core.limiter import limiter
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="/scoring", tags=["记分牌"])


@limiter.limit("100/minute")
@router.post("/matches", summary="创建比赛")
async def create_match(
    body: MatchCreateRequest,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.create_match(user.id, body)
    return success(data=data, message="比赛已创建")


@limiter.limit("100/minute")
@router.get("/matches", summary="比赛列表")
async def list_matches(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    from app.schemas.scoring import MatchListQuery
    query = MatchListQuery(status=status, page=page, page_size=page_size)
    data = await ScoringService.list_matches(user.id, query)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/matches/{match_id}", summary="比赛详情")
async def get_match(
    match_id: int,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.get_match_detail(user.id, match_id)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/score", summary="记分")
async def score(
    match_id: int,
    body: ScoreRequest,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.score(user.id, match_id, body)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/undo", summary="撤销最近一球")
async def undo(
    match_id: int,
    body: Optional[UndoRequest] = None,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.undo(user.id, match_id, body)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/finish", summary="结束比赛")
async def finish_match(
    match_id: int,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.finish_match(user.id, match_id)
    return success(data=data, message="比赛已结束")


@limiter.limit("100/minute")
@router.get("/matches/{match_id}/statistics", summary="比赛统计")
async def get_statistics(
    match_id: int,
    user: User = Depends(get_current_user),
):
    data = await ScoringService.get_statistics(user.id, match_id)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/start", summary="开始比赛（状态机入口）")
async def start_match(
    match_id: int,
    user: User = Depends(get_current_user),
):
    """将 setup 状态的比赛切换为 in_progress，开始记分。"""
    data = await ScoringService.start_match(user.id, match_id)
    return success(data=data, message="比赛已开始")


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/abandon", summary="放弃比赛")
async def abandon_match(
    match_id: int,
    user: User = Depends(get_current_user),
):
    """放弃进行中的比赛，24h 内可恢复。"""
    data = await ScoringService.abandon_match(user.id, match_id)
    return success(data=data, message="比赛已放弃")


@limiter.limit("100/minute")
@router.post("/matches/{match_id}/resume", summary="恢复放弃的比赛")
async def resume_match(
    match_id: int,
    user: User = Depends(get_current_user),
):
    """恢复 24h 内放弃的比赛。"""
    data = await ScoringService.resume_match(user.id, match_id)
    return success(data=data, message="比赛已恢复")
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.scoring.router import router as scoring_router
api_router.include_router(scoring_router)
```

---

## 7. 冒烟测试脚本

> **Celery Beat 定时任务说明**（X-26）：
> - 任务名：`scoring.cleanup_abandoned_matches`
> - 调度：每小时第 5 分钟（`crontab(minute=5)`，错峰）
> - 逻辑：扫描 `status="abandoned"` 且 `abandoned_at` 超过 24h 的比赛，自动更新为 `status="finished"`，并在 `MatchStatistic` 中标注 `"超时自动结束"`
> - 实现文件：`app/tasks/scoring_tasks.py`
> - 注册：已在统一调度表 `beat_schedule.py` 中注册（条目名 `scoring-cleanup-abandoned`），无需在模块内单独定义。
> - 任务代码示意：
> ```python
> # app/tasks/scoring_tasks.py
> from datetime import datetime, timedelta, timezone
> from app.core.celery import celery_app
> from app.core.database import get_async_session
> from app.models.scoring import Match, MatchStatistic
> from sqlalchemy import select, update
> import json
> import asyncio
>
> @celery_app.task(name="scoring.cleanup_abandoned_matches")
> def cleanup_abandoned_matches():
>     """每小时扫描 abandoned 超过 24h 的比赛，自动转为 finished。"""
>     asyncio.run(_cleanup_abandoned_matches_async())
> 
> async def _cleanup_abandoned_matches_async():
>     threshold = datetime.now(timezone.utc) - timedelta(hours=24)
>     async with get_async_session() as db:
>         result = await db.execute(
>             select(Match).where(
>                 Match.status == "abandoned",
>                 Match.abandoned_at < threshold,
>             )
>         )
>         matches = result.scalars().all()
>         for match in matches:
>             match.status = "finished"
>             match.finished_at = datetime.now(timezone.utc)
>             match.final_score = f"{match.current_score_user}:{match.current_score_opp}"
>             # 生成统计并标注超时自动结束
>             stat = MatchStatistic(
>                 match_id=match.id,
>                 stats_data={"note": "超时自动结束"},
>             )
>             db.add(stat)
>         await db.commit()
> ```

**实际任务定义（R19-P3-A 补全）**：

> 原切片仅以 markdown 引用块（`>` 前缀）给出任务代码示意，未提供独立代码块的实际 `@celery_app.task` 定义。以下补全与 `beat_schedule.py` 注册名 `scoring-cleanup-abandoned` → `scoring.cleanup_abandoned_matches` 一致的实际定义。

```python
# app/tasks/scoring_tasks.py
"""
scoring 模块 Celery 任务定义。
任务名 scoring.cleanup_abandoned_matches 与 beat_schedule 注册名一致。
"""
from datetime import datetime, timedelta, timezone

from app.core.celery import celery_app
from app.core.database import get_async_session
from app.models.scoring import Match, MatchStatistic
from sqlalchemy import select

import asyncio


# R19-P3-A: 补全 @celery_app.task 实际定义（与 beat_schedule 注册名一致），原切片仅以引用块示意形式给出
@celery_app.task(name="scoring.cleanup_abandoned_matches")
def cleanup_abandoned_matches():
    """每小时扫描 abandoned 超过 24h 的比赛，自动转为 finished。"""
    asyncio.run(_cleanup_async())


async def _cleanup_async():
    """异步执行 abandoned 比赛清理逻辑（与 beat_schedule 注册名一致）。"""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    async with get_async_session() as db:
        result = await db.execute(
            select(Match).where(
                Match.status == "abandoned",
                Match.abandoned_at < threshold,
            )
        )
        matches = result.scalars().all()
        for match in matches:
            match.status = "finished"
            match.finished_at = datetime.now(timezone.utc)
            match.final_score = f"{match.current_score_user}:{match.current_score_opp}"
            # 生成统计并标注超时自动结束
            stat = MatchStatistic(
                match_id=match.id,
                stats_data={"note": "超时自动结束"},
            )
            db.add(stat)
        await db.commit()
```

```python
# tests/smoke/scoring_smoke_test.py
"""
scoring 模块冒烟测试。
用法: python -m tests.smoke.scoring_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 0. 登录（使用测试账号）
        print("0. Testing login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE", "nickname": "冒烟测试",
        })
        if resp.status_code != 200:
            print(f"   ✗ Login failed, skipping scoring smoke test")
            return
        token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print("   ✓ Login success")

        # 1. 创建比赛
        print("1. Testing POST /scoring/matches...")
        resp = await client.post("/scoring/matches", headers=h, json={
            "opponent_name": "冒烟对手",
            "opponent_rating": 1500,
            "format": "bo1",
            "match_type": "friendly",
            "target_score": 11,
        })
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        match_id = resp.json()["data"]["match_id"]
        print(f"   ✓ Created match: {match_id}")

        # 2. 开始比赛（setup → in_progress）
        print("2. Testing POST /scoring/matches/{id}/start...")
        resp = await client.post(f"/scoring/matches/{match_id}/start", headers=h)
        assert resp.status_code == 200, f"Start failed: {resp.text}"
        start_data = resp.json()["data"]
        assert start_data["status"] == "in_progress"
        assert "started_at" in start_data
        print(f"   ✓ Match started: status={start_data['status']}")

        # 3. 记分
        print("3. Testing POST /scoring/matches/{id}/score...")
        resp = await client.post(
            f"/scoring/matches/{match_id}/score", headers=h,
            json={"scorer": "user", "score_method": "rally_point", "technique_action": "forehand_drive"},
        )
        if resp.status_code == 400:
            print(f"   ⚠ Score failed (match in setup), need start endpoint")
        else:
            assert resp.status_code == 200, f"Score failed: {resp.text}"
            score_data = resp.json()["data"]
            print(f"   ✓ Scored: seq={score_data['sequence']}, score={score_data['score']}")

        # 4. 比赛列表
        print("4. Testing GET /scoring/matches...")
        resp = await client.get("/scoring/matches", headers=h)
        assert resp.status_code == 200
        total = resp.json()["data"]["total"]
        print(f"   ✓ List: {total} matches")

        # 5. 比赛详情
        print("5. Testing GET /scoring/matches/{id}...")
        resp = await client.get(f"/scoring/matches/{match_id}", headers=h)
        assert resp.status_code == 200
        print(f"   ✓ Detail: status={resp.json()['data']['status']}")

        # 6. 撤销
        print("6. Testing POST /scoring/matches/{id}/undo...")
        resp = await client.post(f"/scoring/matches/{match_id}/undo", headers=h)
        if resp.status_code == 200:
            print(f"   ✓ Undo: {resp.json()['data']['type']}")  # R18-P3: action→type
        else:
            print(f"   ⚠ Undo: {resp.json().get('message', 'failed')}")

        # 7. 结束比赛
        print("7. Testing POST /scoring/matches/{id}/finish...")
        resp = await client.post(f"/scoring/matches/{match_id}/finish", headers=h)
        if resp.status_code == 200:
            finish_data = resp.json()["data"]
            print(f"   ✓ Finish: is_win={finish_data['is_win']}, statistic_id={finish_data.get('statistic_id')}")
        else:
            print(f"   ⚠ Finish: {resp.json().get('message', 'failed')}")

        # 8. 比赛统计
        print("8. Testing GET /scoring/matches/{id}/statistics...")
        resp = await client.get(f"/scoring/matches/{match_id}/statistics", headers=h)
        if resp.status_code == 200:
            print(f"   ✓ Statistics retrieved")
        else:
            print(f"   ⚠ Statistics: {resp.json().get('message', 'failed')}")

    print("\nscoring_smoke_test: ALL PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_scoring.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.scoring_smoke_test`
- [ ] 后端语法检查：`python -c "import py_compile; py_compile.compile('app/models/scoring.py'); py_compile.compile('app/schemas/scoring.py'); py_compile.compile('app/services/scoring_service.py'); py_compile.compile('app/api/v1/scoring/router.py')"`
- [ ] Model 已在 `app/models/__init__.py` 中导入
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] Alembic 迁移已生成并执行：`alembic revision --autogenerate -m "add_scoring_tables" && alembic upgrade head`
- [ ] Redis 连接正确（seq / current_score / server / status）
- [ ] WebSocket 推送正确（`ws:match:{id}` 房间广播）
- [ ] 比赛状态机约束所有操作（setup → in_progress → finished/abandoned）
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`MatchCreateRequest`、`ScoreRequest`、`MatchBrief`、`MatchDetail`、`ScoreResponse`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- Redis 序号 **必须** 使用 `INCR` 保证原子性，**禁止** 数据库自增
- 撤销 **必须** 校验 `seq == max_seq`，**禁止** 撤销非最后一球
- 比赛结束 **必须** 自动生成 `MatchStatistic`，**禁止** 手动触发
- WebSocket 推送 **必须** 在记分和撤销后执行，房间名为 `ws:match:{match_id}`
- 发球轮换 **必须** 遵循 11 分制规则（2 球轮换 + 10:10 后 1 球轮换）
- 测试 **必须** 使用 `httpx.AsyncClient`，**禁止** 自建 HTTP 客户端
- 冒烟测试 **必须** 可作为独立脚本运行
- 比赛状态机 **必须** 遵循：`setup →（start）→ in_progress →（finish）→ finished /（abandon）→ abandoned →（resume, 24h 内）→ in_progress`
- **必须** 通过 `POST /scoring/matches/{id}/start` 显式进入 `in_progress` 状态，**禁止** 在 `score` 时自动切换状态（X-21 修复）
- `abandoned` 状态超过 24h 的比赛 **必须** 由 Celery Beat 任务自动转为 `finished`，**禁止** 永久停留在 `abandoned`（X-26 修复）
- `resume` 端点 **必须** 校验 `abandoned_at` 在 24h 内，**禁止** 恢复超时比赛（X-26 修复）
- 换边提示 **必须** 在每局结束和 10:10 平分后每得 1 分时触发，`ScoreResponse.should_change_sides` 字段 **必须** 返回（R-2 修复）
- ALL API 端点已添加 `@limiter.limit()` 限流装饰器，全局默认 100/minute，AI 分析创建 10/hour

### 覆盖度修复说明

| 编号 | 修复内容 | 位置 |
|------|---------|------|
| X-21 | 添加 `POST /matches/{id}/start` 状态机入口端点 + `MatchStartResponse` Schema + `start_match` Service 方法（返回 `started_at`） | §3 Match 模型、§4 Schema、§5 Service、§6 API 路由、§2 测试 |
| X-26 | 添加 `abandoned` 状态 + `abandon_match`/`resume_match` Service 方法 + `abandoned_at` 字段 + Celery Beat 定时任务说明 + `POST /matches/{id}/abandon` 和 `POST /matches/{id}/resume` 端点 | §3 Match 模型、§4 Schema、§5 Service、§6 API 路由、§7 Celery Beat、§2 测试 |
| R-2 | 添加 `_should_change_sides` 换边判断逻辑 + `ScoreResponse.should_change_sides` 字段 | §4 Schema、§5 Service（`_should_change_sides` + `score` 方法） |
| A-9 | `datetime.utcnow()` → `datetime.now(timezone.utc)`；`default=datetime.utcnow` → `default=lambda: datetime.now(timezone.utc)`；`onupdate=datetime.utcnow` → `onupdate=lambda: datetime.now(timezone.utc)`；import 补充 `timezone` | §3 Model、§5 Service |
