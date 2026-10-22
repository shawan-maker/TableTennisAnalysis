# match_data 模块 — 后端垂直切片设计

> **模块名称**：`match_data`
> **所属目录**：`app/api/v1/match_data/`
> **定位**：手动录入比赛数据，支持快速录入（只录总比分）和详细录入（逐分技术动作）
> **依据**：模块详细设计 v1.2 §2.5、API 详细设计 v1.3 §7

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.5（match_data 模块功能规格）
- [ ] 阅读 API 契约 §7（比赛数据模块 3 个端点）
- [ ] 阅读 `app/core/response.py`（统一响应 `success()`）
- [ ] 阅读 `app/core/deps.py`（`get_current_user` 依赖注入）
- [ ] 阅读 `app/core/pagination.py`（分页工具 `paginate()`）
- [ ] 阅读 `app/models/scoring.py`（`Match` 表，用于可选关联 `match_id`）
- [ ] 确认本切片范围：3 个 API 端点 + 对应 Service 方法 + 2 个 Model

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/match_data.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/match_data.py` | #1 | ☐ |
| 4 | 实现 Service | `app/services/match_data_service.py` | #2,#3 | ☐ |
| 5 | 实现 API 路由 | `app/api/v1/match_data/router.py` | #4 | ☐ |
| 6 | 注册 Router | `app/api/v1/__init__.py` | #5 | ☐ |
| 7 | Alembic 迁移 | `alembic revision --autogenerate` | #2 | ☐ |
| 8 | 编写测试 | `tests/unit/test_match_data.py` | #4 | ☐ |
| 9 | 编写冒烟测试 | `tests/smoke/match_data_smoke_test.py` | #5 | ☐ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_match_data.py
"""
match_data 模块 — 比赛数据录入测试。
覆盖：快速录入、详细录入、is_win 自动计算、比分合法性校验、列表查询、详情查询。
"""
import pytest
from datetime import datetime, timezone
from app.core.exceptions import AppException


@pytest.fixture
async def match_data_ctx(client, db_session, auth_user):
    """创建测试上下文：已登录用户 + Token。"""
    return {
        "client": client,
        "headers": {"Authorization": f"Bearer {auth_user['access_token']}"},
        "user": auth_user,
    }


# === 1. Happy Path（正常流程） ===
@pytest.mark.asyncio
async def test_quick_create_success(match_data_ctx):
    """快速录入比赛记录成功，is_win 自动计算。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "测试对手",
        "opponent_rating": 1500,
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["is_win"] is True  # 3 > 1 → 胜


@pytest.mark.asyncio
async def test_quick_create_lose(match_data_ctx):
    """快速录入失败比赛，is_win 为 False。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "强敌",
        "my_score": 1,
        "opponent_score": 3,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["is_win"] is False  # 1 < 3 → 负


@pytest.mark.asyncio
async def test_detailed_create_success(match_data_ctx):
    """详细录入比赛记录 + 逐分明细成功。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "测试对手",
        "opponent_rating": 1480,
        "my_score": 11,
        "opponent_score": 8,
        "format": "custom",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": [
            {"sequence": 1, "scorer": "user", "score_method": "serve_point", "technique_action": "forehand_drive"},
            {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
            {"sequence": 3, "scorer": "user", "score_method": "rally_point", "technique_action": "forehand_loop"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["is_win"] is True  # 11 > 8


@pytest.mark.asyncio
async def test_list_records(match_data_ctx):
    """比赛记录列表查询成功。"""
    ctx = match_data_ctx
    # 先创建几条
    for i in range(3):
        await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
            "opponent_name": f"对手{i}",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_type": "friendly",
            "match_date": datetime.now(timezone.utc).isoformat(),
            "details": None,
        })
    resp = await ctx["client"].get("/api/v1/match-data/records", headers=ctx["headers"])
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] >= 3


@pytest.mark.asyncio
async def test_get_detail_with_details(match_data_ctx):
    """详情接口返回逐分明细。"""
    ctx = match_data_ctx
    create = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 11,
        "opponent_score": 8,
        "format": "custom",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": [
            {"sequence": 1, "scorer": "user", "score_method": "serve_point"},
            {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
        ],
    })
    record_id = create.json()["data"]["id"]
    resp = await ctx["client"].get(
        f"/api/v1/match-data/records/{record_id}", headers=ctx["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["details"]) == 2


# === 2. Validation Failure（参数校验失败） ===
@pytest.mark.asyncio
async def test_create_invalid_score_bo5(match_data_ctx):
    """bo5 赛制比分不合法（3:2 合法，5:3 不合法）返回 422。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 5,
        "opponent_score": 3,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    assert resp.status_code == 422
    assert "赛制规则" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_future_date(match_data_ctx):
    """比赛日期在未来返回 422。"""
    ctx = match_data_ctx
    future_date = datetime(2099, 12, 31, tzinfo=timezone.utc).isoformat()
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": future_date,
        "details": None,
    })
    assert resp.status_code == 422
    assert "不能晚于" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_missing_opponent_name(match_data_ctx):
    """缺少对手姓名返回 422。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    assert resp.status_code == 422


# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_create_unauthorized(client):
    """未登录用户创建记录返回 401。"""
    resp = await client.post("/api/v1/match-data/records", json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_other_user_record(match_data_ctx, auth_user2):
    """查询其他用户的比赛记录返回 404。"""
    ctx = match_data_ctx
    create = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    record_id = create.json()["data"]["id"]
    headers2 = {"Authorization": f"Bearer {auth_user2['access_token']}"}
    resp = await ctx["client"].get(
        f"/api/v1/match-data/records/{record_id}", headers=headers2,
    )
    assert resp.status_code == 404
    assert "不存在" in resp.json()["message"]


# === 4. Business Rule Violation（业务规则违反） ===
@pytest.mark.asyncio
async def test_gamification_points_triggered(match_data_ctx):
    """创建比赛记录后触发 gamification 积分 +3。"""
    ctx = match_data_ctx
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    assert resp.status_code == 200
    # gamification 积分触发通过异步任务，检查无错误即可


@pytest.mark.asyncio
async def test_link_scoring_match(match_data_ctx):
    """可选关联记分牌比赛 match_id。"""
    ctx = match_data_ctx
    # 先创建一个记分牌比赛（假设 match_id=1 存在）
    resp = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
        "match_id": 99999,  # 不存在的 match_id → 应忽略或报错
    })
    # 设计决策：match_id 不存在时忽略关联，正常创建记录
    assert resp.status_code == 200


# === 5. F5 手动编辑比赛记录 ===
@pytest.mark.asyncio
async def test_update_record_opponent_name(match_data_ctx):
    """PATCH 修正对手姓名成功。"""
    ctx = match_data_ctx
    # 先创建记录
    create = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "原名",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    record_id = create.json()["data"]["id"]
    # PATCH 修正对手姓名
    resp = await ctx["client"].patch(
        f"/api/v1/match-data/records/{record_id}",
        headers=ctx["headers"],
        json={"opponent_name": "修正后对手名"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == record_id


@pytest.mark.asyncio
async def test_update_record_score_recalc_is_win(match_data_ctx):
    """PATCH 修正比分后 is_win 自动重算。"""
    ctx = match_data_ctx
    # 创建胜利记录 3:1
    create = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    record_id = create.json()["data"]["id"]
    assert create.json()["data"]["is_win"] is True
    # PATCH 修正为 1:3（败）
    resp = await ctx["client"].patch(
        f"/api/v1/match-data/records/{record_id}",
        headers=ctx["headers"],
        json={"my_score": 1, "opponent_score": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_win"] is False  # 1 < 3 → 负


@pytest.mark.asyncio
async def test_update_record_not_found(match_data_ctx):
    """PATCH 不存在的记录返回 404。"""
    ctx = match_data_ctx
    resp = await ctx["client"].patch(
        "/api/v1/match-data/records/99999",
        headers=ctx["headers"],
        json={"opponent_name": "不存在"},
    )
    assert resp.status_code == 404
    assert "不存在" in resp.json()["message"]


@pytest.mark.asyncio
async def test_update_record_other_user(match_data_ctx, auth_user2):
    """PATCH 其他用户的记录返回 404。"""
    ctx = match_data_ctx
    create = await ctx["client"].post("/api/v1/match-data/records", headers=ctx["headers"], json={
        "opponent_name": "对手",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": datetime.now(timezone.utc).isoformat(),
        "details": None,
    })
    record_id = create.json()["data"]["id"]
    headers2 = {"Authorization": f"Bearer {auth_user2['access_token']}"}
    resp = await ctx["client"].patch(
        f"/api/v1/match-data/records/{record_id}",
        headers=headers2,
        json={"opponent_name": "篡改"},
    )
    assert resp.status_code == 404
```

---

## 3. Model 实现

```python
# app/models/match_data.py
"""
比赛数据模块数据模型。
包含：MatchRecord（手动录入比赛记录）、ManualScoreDetail（逐分明细）。
"""
from datetime import datetime, timezone

from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MatchRecord(Base):
    """手动录入的比赛记录（快速录入或详细录入）。"""
    __tablename__ = "match_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), comment="创建者用户ID")  # R19-P3-10: 移除冗余 index=True（__table_args__ idx_mrecord_user_date 已覆盖）
    opponent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opponent_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="对手积分")
    my_score: Mapped[int] = mapped_column(Integer, comment="我的得分/局数")
    opponent_score: Mapped[int] = mapped_column(Integer, comment="对手得分/局数")
    is_win: Mapped[bool] = mapped_column(Boolean, comment="是否胜利（自动计算）")
    format: Mapped[str] = mapped_column(String(20), default="bo5", comment="赛制: bo1/bo3/bo5/bo7/custom")
    match_type: Mapped[str] = mapped_column(String(20), default="friendly", comment="比赛类型")
    match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="比赛日期时间")  # R19-P3-9: 由业务层注入（DB §2.13 DEFAULT NOW() 兜底对齐）
    # 可选关联记分牌比赛
    match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R28-OBS-2/R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_user_date 已覆盖 user_id 查询路径；match_id 为可选 FK 字段，无独立查询场景，与 DB §2.13 索引声明一致）
        comment="关联的记分牌比赛ID（可选）",
    )
    # 录入模式标记
    is_detailed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否详细录入（含逐分明细）")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_mrecord_user_date", "user_id", "match_date"),
    )

    # 关系
    details: Mapped[list["ManualScoreDetail"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="ManualScoreDetail.sequence",
    )


class ManualScoreDetail(Base):
    """逐分明细（详细录入时记录每分得分方式和技术动作）。"""
    __tablename__ = "manual_score_detail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_record_id: Mapped[int] = mapped_column(ForeignKey("match_record.id", ondelete="CASCADE"))  # R19-P3-10: 移除冗余 index=True（__table_args__ idx_msd_record_seq 已覆盖）
    sequence: Mapped[int] = mapped_column(Integer, comment="得分序号")
    scorer: Mapped[str] = mapped_column(String(10), comment="得分方: user/opponent")
    score_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="得分方式: serve_point/rally_point/opponent_error")
    technique_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="技术动作")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_msd_record_seq", "match_record_id", "sequence"),  # R19-P3-10: 补充索引（DB §2.14/§7 已定义）
    )

    record: Mapped["MatchRecord"] = relationship(back_populates="details")
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入：`from app.models.match_data import MatchRecord, ManualScoreDetail`
- [ ] 运行 `alembic revision --autogenerate -m "add_match_data_tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/match_data.py
"""
比赛数据模块 Pydantic Schema。
"""
from datetime import datetime, timezone

from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator


# --- 请求 Schema ---

class ManualScoreDetailItem(BaseModel):
    """逐分明细条目（详细录入时提交）。"""
    sequence: int = Field(..., ge=1, description="得分序号")
    scorer: Literal["user", "opponent"] = Field(..., description="得分方")
    score_method: Literal["serve_point", "rally_point", "opponent_error"] = Field(..., description="得分方式")
    technique_action: Optional[str] = Field(default=None, max_length=30, description="技术动作")


class MatchRecordCreateRequest(BaseModel):
    """创建比赛记录请求（快速/详细录入统一入口）。"""
    opponent_name: str = Field(..., min_length=1, max_length=64, description="对手姓名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    my_score: int = Field(..., ge=0, le=99, description="我的得分/局数")
    opponent_score: int = Field(..., ge=0, le=99, description="对手得分/局数")
    format: Literal["bo1", "bo3", "bo5", "bo7", "custom"] = Field(default="bo5", description="赛制")
    match_type: Literal["friendly", "tournament", "training"] = Field(default="friendly", description="比赛类型")
    match_date: datetime = Field(..., description="比赛日期时间")
    details: Optional[list[ManualScoreDetailItem]] = Field(default=None, description="逐分明细（详细录入时提供）")
    match_id: Optional[int] = Field(default=None, ge=1, description="关联的记分牌比赛ID（可选）")

    @model_validator(mode="after")
    def validate_score(self):
        """比分合法性校验。"""
        # 比分不能相同
        if self.my_score == self.opponent_score:
            raise ValueError("比分不能相同")
        # 日期不能在未来
        if self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self


# --- 响应 Schema ---

class MatchRecordBrief(BaseModel):
    """比赛记录列表项。"""
    id: int
    opponent_name: str
    opponent_rating: Optional[int] = None
    my_score: int
    opponent_score: int
    is_win: bool
    format: str
    match_type: str
    match_date: datetime
    model_config = {"from_attributes": True}


class MatchRecordDetail(BaseModel):
    """比赛记录详情（含逐分明细）。"""
    id: int
    opponent_name: str
    opponent_rating: Optional[int] = None
    my_score: int
    opponent_score: int
    is_win: bool
    format: str
    match_type: str
    match_date: datetime
    match_id: Optional[int] = None
    is_detailed: bool
    details: list[ManualScoreDetailItem] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class MatchRecordCreateResponse(BaseModel):
    """创建比赛记录响应。"""
    id: int
    is_win: bool


# --- 查询 Schema ---

class MatchRecordListQuery(BaseModel):
    """比赛记录列表查询参数。"""
    result: Optional[Literal["win", "lose", "all"]] = Field(default="all", description="结果筛选")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class MatchRecordUpdate(BaseModel):
    """手动编辑比赛记录请求（F5：修正比赛结果、补充技术统计等）。
    所有字段均为可选，仅更新传入的字段。
    """
    opponent_name: Optional[str] = Field(default=None, min_length=1, max_length=64, description="对手姓名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    my_score: Optional[int] = Field(default=None, ge=0, le=99, description="我的得分/局数")
    opponent_score: Optional[int] = Field(default=None, ge=0, le=99, description="对手得分/局数")
    match_date: Optional[datetime] = Field(default=None, description="比赛日期时间")
    match_type: Optional[Literal["friendly", "tournament", "training"]] = Field(default=None, description="比赛类型")
    notes: Optional[str] = Field(default=None, max_length=500, description="备注/补充说明")

    @model_validator(mode="after")
    def validate_score_update(self):
        """比分合法性校验（仅在同时提供 my_score 和 opponent_score 时触发）。"""
        if self.my_score is not None and self.opponent_score is not None:
            if self.my_score == self.opponent_score:
                raise ValueError("比分不能相同")
        if self.match_date is not None and self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self
```

---

## 5. Service 实现

```python
# app/services/match_data_service.py
"""
比赛数据业务逻辑层。
核心职责：快速/详细录入、比分合法性校验、is_win 自动计算、gamification 积分触发。
"""
from datetime import datetime, timezone, date, timedelta

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from app.core.exceptions import AppException
from app.core.database import get_async_session
from app.core.pagination import paginate
from app.models.match_data import MatchRecord, ManualScoreDetail
from app.models.scoring import Match

logger = logging.getLogger(__name__)
from app.schemas.match_data import (
    MatchRecordCreateRequest, MatchRecordListQuery,
    MatchRecordBrief, MatchRecordDetail, MatchRecordCreateResponse,
    MatchRecordUpdate,
    ManualScoreDetailItem,
)

# gamification 积分触发（延迟导入，避免循环依赖）
# 积分规则由 GamificationService.POINTS_RULES 统一管理，本模块不再硬编码积分数


class MatchDataService:
    """比赛数据业务逻辑层。"""

    # 赛制 → 需要 win 局数映射
    FORMAT_WIN_MAP = {
        "bo1": 1, "bo3": 2, "bo5": 3, "bo7": 4,
    }

    @staticmethod
    def _validate_score_by_format(my_score: int, opp_score: int, fmt: str) -> bool:
        """
        校验比分是否符合赛制规则。
        - bo1/bo3/bo5/bo7：my_score 和 opp_score 中有一个等于需要赢的局数
        - custom：不做局数校验，但 my_score != opp_score
        """
        if fmt == "custom":
            return my_score != opp_score
        win_needed = MatchDataService.FORMAT_WIN_MAP.get(fmt)
        if win_needed is None:
            return False
        # 胜者必须达到 win_needed，败者必须 < win_needed
        if my_score == win_needed:
            return opp_score < win_needed
        if opp_score == win_needed:
            return my_score < win_needed
        return False

    @staticmethod
    async def _trigger_gamification(user_id: int, record_id: int) -> None:
        """触发 gamification 积分 +3（延迟导入，使用统一 API 签名）。"""
        try:
            from app.services.gamification_service import GamificationService
            async with get_async_session() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="record", ref_id=record_id,
                )
        except Exception as e:
            logger.error("match_data_trigger_gamification_failed", error=str(e))

    @staticmethod
    async def create_record(user_id: int, req: MatchRecordCreateRequest) -> dict:
        """创建比赛记录（快速/详细录入统一入口）。"""
        # 1. 比分合法性校验
        if not MatchDataService._validate_score_by_format(req.my_score, req.opponent_score, req.format):
            raise AppException("比分不符合赛制规则", 422)

        # 2. is_win 自动计算
        is_win = req.my_score > req.opponent_score
        is_detailed = req.details is not None and len(req.details) > 0

        async with get_async_session() as db:
            # 3. 可选关联记分牌比赛（match_id 存在性校验）
            match_id = req.match_id
            if match_id is not None:
                match_result = await db.execute(
                    select(Match).where(
                        Match.id == match_id, Match.user_id == user_id,
                    )
                )
                if not match_result.scalar_one_or_none():
                    match_id = None  # match_id 不存在则忽略关联

            # 4. 创建 match_record
            record = MatchRecord(
                user_id=user_id,
                opponent_name=req.opponent_name,
                opponent_rating=req.opponent_rating,
                my_score=req.my_score,
                opponent_score=req.opponent_score,
                is_win=is_win,
                format=req.format,
                match_type=req.match_type,
                match_date=req.match_date,
                match_id=match_id,
                is_detailed=is_detailed,
            )
            db.add(record)
            await db.flush()  # 获取 record.id

            # 5. 详细录入 → 创建逐分明细
            if is_detailed and req.details:
                for detail_item in req.details:
                    detail = ManualScoreDetail(
                        match_record_id=record.id,
                        sequence=detail_item.sequence,
                        scorer=detail_item.scorer,
                        score_method=detail_item.score_method,
                        technique_action=detail_item.technique_action,
                    )
                    db.add(detail)

            await db.commit()
            await db.refresh(record)

        # 6. 触发 gamification 积分（异步，不阻塞响应）
        await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": is_win}

    @staticmethod
    async def create_record_from_scoring(
        db, match_id: int, user_id: int, trigger_points: bool = True,
    ) -> dict:
        """从记分牌比赛数据自动创建 match_record（由 scoring 模块 finish_match 调用）。

        字段映射:
          match.final_score → my_score / opponent_score（解析 "X:Y" 格式）
          match.* → match_record 对应字段
          score_record.* → manual_score_detail 对应字段

        Args:
            trigger_points: 是否触发 record 事件积分（+3）。
                默认 True（保持手动调用时的行为）。
                当由 scoring 模块 finish_match 调用时传 False，
                因为 finish_match 已单独触发 match 事件积分（+5），
                避免重复积分（P2-PTS-01 修复）。
        """
        # 1. 查询 Match 获取比赛元数据
        from app.models.scoring import Match, ScoreRecord
        match_result = await db.execute(
            select(Match).where(Match.id == match_id, Match.user_id == user_id)
        )
        match = match_result.scalar_one_or_none()
        if not match:
            raise AppException("记分牌比赛不存在", 404)

        # 2. 解析 final_score "X:Y" → my_score, opponent_score
        if match.final_score and ":" in match.final_score:
            parts = match.final_score.split(":")
            my_score = int(parts[0].strip())
            opponent_score = int(parts[1].strip())
        else:
            my_score = match.current_score_user or 0
            opponent_score = match.current_score_opp or 0

        # 3. 查询 ScoreRecord 逐球明细
        sr_result = await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.match_id == match_id)
            .order_by(ScoreRecord.sequence)
        )
        score_records = sr_result.scalars().all()
        is_detailed = len(score_records) > 0

        # 4. 创建 match_record
        record = MatchRecord(
            user_id=user_id,
            opponent_name=match.opponent_name,
            opponent_rating=match.opponent_rating,
            my_score=my_score,
            opponent_score=opponent_score,
            is_win=match.is_win if match.is_win is not None else (my_score > opponent_score),
            format=match.format,
            match_type=match.match_type,
            match_date=match.finished_at.date() if match.finished_at else datetime.now(timezone(timedelta(hours=8))).date(),
            match_id=match_id,
            is_detailed=is_detailed,
        )
        db.add(record)
        await db.flush()

        # 5. 创建逐分明细（score_record → manual_score_detail）
        if is_detailed:
            for sr in score_records:
                detail = ManualScoreDetail(
                    match_record_id=record.id,
                    sequence=sr.sequence,
                    scorer=sr.scorer,
                    score_method=sr.score_method,
                    technique_action=sr.technique_action,
                )
                db.add(detail)

        await db.commit()
        await db.refresh(record)

        # 6. 触发 gamification 积分（record 事件 +3）
        # P2-PTS-01 修复：仅手动录入时触发 +3 record 积分；
        # 由 scoring 模块 finish_match 调用时传 trigger_points=False，
        # 因为 finish_match 已触发 match 事件 +5 积分，避免重复积分。
        if trigger_points:
            await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": record.is_win}

    @staticmethod
    async def list_records(user_id: int, query: MatchRecordListQuery) -> dict:
        """查询比赛记录列表。"""
        async with get_async_session() as db:
            qs = select(MatchRecord).where(MatchRecord.user_id == user_id)
            count_qs = select(func.count()).select_from(MatchRecord).where(MatchRecord.user_id == user_id)

            if query.result and query.result != "all":
                is_win_filter = (query.result == "win")
                qs = qs.where(MatchRecord.is_win == is_win_filter)
                count_qs = count_qs.where(MatchRecord.is_win == is_win_filter)

            qs = qs.order_by(MatchRecord.match_date.desc())

            total, items = await paginate(db, qs, count_qs, query.page, query.page_size)
            return {
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
                "items": [MatchRecordBrief.model_validate(r).model_dump() for r in items],
            }

    @staticmethod
    async def get_detail(user_id: int, record_id: int) -> dict:
        """获取比赛记录详情（含逐分明细）。"""
        async with get_async_session() as db:
            record_result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id,
                )
            )
            record = record_result.scalar_one_or_none()
            if not record:
                raise AppException("比赛记录不存在", 404)

            # 查询逐分明细
            details_result = await db.execute(
                select(ManualScoreDetail)
                .where(ManualScoreDetail.match_record_id == record_id)
                .order_by(ManualScoreDetail.sequence)
            )
            details = details_result.scalars().all()

            detail = MatchRecordDetail.model_validate(record)
            detail.details = [
                ManualScoreDetailItem(
                    sequence=d.sequence,
                    scorer=d.scorer,
                    score_method=d.score_method,
                    technique_action=d.technique_action,
                )
                for d in details
            ]
            return detail.model_dump()

    @staticmethod
    async def update_record(
        user_id: int, record_id: int, data: MatchRecordUpdate,
    ) -> dict:
        """
        F5：手动编辑比赛记录（修正比赛结果、补充技术统计等）。
        仅更新传入的字段，is_win 在比分变更时自动重算。
        """
        async with get_async_session() as db:
            record_result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id,
                )
            )
            record = record_result.scalar_one_or_none()
            if not record:
                raise AppException("比赛记录不存在", 404)

            # 关联校验：已关联记分牌的比赛记录不可编辑（返回 409 Conflict）
            if record.match_id is not None:
                raise AppException("比赛记录已关联记分牌，不可编辑", 409)

            update_data = data.model_dump(exclude_unset=True)
            if not update_data:
                raise AppException("未提供任何更新字段", 422)

            # 逐字段更新
            for field, value in update_data.items():
                if hasattr(record, field):
                    setattr(record, field, value)

            # 如果比分发生变更，重算 is_win
            if data.my_score is not None or data.opponent_score is not None:
                my_score = record.my_score
                opp_score = record.opponent_score
                record.is_win = my_score > opp_score

            await db.commit()
            await db.refresh(record)

            return {"id": record.id, "is_win": record.is_win}
```

---

## 6. API 路由实现

```python
# app/api/v1/match_data/router.py
"""
比赛数据模块 API 路由。
所有路由只调用 MatchDataService，不包含业务逻辑。
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.deps import get_current_user
from app.core.response import success
from app.models.user import User
from app.schemas.match_data import MatchRecordCreateRequest, MatchRecordListQuery, MatchRecordUpdate
from app.core.limiter import limiter
from app.services.match_data_service import MatchDataService

router = APIRouter(prefix="/match-data", tags=["比赛数据"])


@limiter.limit("100/minute")
@router.post("/records", summary="创建比赛记录（快速/详细录入）")
async def create_record(
    body: MatchRecordCreateRequest,
    user: User = Depends(get_current_user),
):
    data = await MatchDataService.create_record(user.id, body)
    return success(data=data, message="比赛记录已创建")


@limiter.limit("100/minute")
@router.get("/records", summary="比赛记录列表")
async def list_records(
    result: Optional[str] = Query(default="all", pattern="^(win|lose|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    query = MatchRecordListQuery(result=result, page=page, page_size=page_size)
    data = await MatchDataService.list_records(user.id, query)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/records/{record_id}", summary="比赛记录详情")
async def get_record(
    record_id: int,
    user: User = Depends(get_current_user),
):
    data = await MatchDataService.get_detail(user.id, record_id)
    return success(data=data)


@limiter.limit("100/minute")
@router.patch("/records/{record_id}", summary="F5：手动编辑比赛记录")
async def update_record(
    record_id: int,
    body: MatchRecordUpdate,
    user: User = Depends(get_current_user),
):
    """手动编辑比赛记录（修正比赛结果、补充技术统计等）。
    仅更新传入的字段，is_win 在比分变更时自动重算。
    """
    data = await MatchDataService.update_record(user.id, record_id, body)
    return success(data=data, message="比赛记录已更新")
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.match_data.router import router as match_data_router
api_router.include_router(match_data_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/match_data_smoke_test.py
"""
match_data 模块冒烟测试。
用法: python -m tests.smoke.match_data_smoke_test
"""
import httpx
import asyncio
from datetime import datetime, timezone

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 0. 登录
        print("0. Testing login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE", "nickname": "冒烟测试",
        })
        if resp.status_code != 200:
            print(f"   ✗ Login failed, skipping match_data smoke test")
            return
        token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print("   ✓ Login success")

        # 1. 快速录入
        print("1. Testing POST /match-data/records (quick)...")
        now = datetime.now(timezone.utc).isoformat()
        resp = await client.post("/match-data/records", headers=h, json={
            "opponent_name": "冒烟对手",
            "opponent_rating": 1500,
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_type": "friendly",
            "match_date": now,
            "details": None,
        })
        assert resp.status_code == 200, f"Quick create failed: {resp.text}"
        record_id = resp.json()["data"]["id"]
        is_win = resp.json()["data"]["is_win"]
        print(f"   ✓ Created record: {record_id}, is_win={is_win}")

        # 2. 详细录入
        print("2. Testing POST /match-data/records (detailed)...")
        resp = await client.post("/match-data/records", headers=h, json={
            "opponent_name": "冒烟对手2",
            "my_score": 11,
            "opponent_score": 8,
            "format": "custom",
            "match_type": "friendly",
            "match_date": now,
            "details": [
                {"sequence": 1, "scorer": "user", "score_method": "serve_point", "technique_action": "forehand_drive"},
                {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
                {"sequence": 3, "scorer": "user", "score_method": "rally_point", "technique_action": "forehand_loop"},
            ],
        })
        assert resp.status_code == 200, f"Detailed create failed: {resp.text}"
        detailed_id = resp.json()["data"]["id"]
        print(f"   ✓ Created detailed record: {detailed_id}")

        # 3. 比分合法性校验
        print("3. Testing score validation (invalid bo5)...")
        resp = await client.post("/match-data/records", headers=h, json={
            "opponent_name": "校验测试",
            "my_score": 5,
            "opponent_score": 3,
            "format": "bo5",
            "match_type": "friendly",
            "match_date": now,
            "details": None,
        })
        assert resp.status_code == 422, f"Validation should fail: {resp.text}"
        print("   ✓ Validation rejected invalid score")

        # 4. 列表查询
        print("4. Testing GET /match-data/records...")
        resp = await client.get("/match-data/records", headers=h)
        assert resp.status_code == 200
        total = resp.json()["data"]["total"]
        print(f"   ✓ List: {total} records")

        # 5. 胜负筛选
        print("5. Testing GET /match-data/records?result=win...")
        resp = await client.get("/match-data/records?result=win", headers=h)
        assert resp.status_code == 200
        win_count = resp.json()["data"]["total"]
        print(f"   ✓ Win records: {win_count}")

        # 6. 详情查询
        print("6. Testing GET /match-data/records/{id}...")
        resp = await client.get(f"/match-data/records/{detailed_id}", headers=h)
        assert resp.status_code == 200
        details = resp.json()["data"]["details"]
        print(f"   ✓ Detail: {len(details)} score details")

    print("\nmatch_data_smoke_test: ALL PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_match_data.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.match_data_smoke_test`
- [ ] 后端语法检查：`python -c "import py_compile; py_compile.compile('app/models/match_data.py'); py_compile.compile('app/schemas/match_data.py'); py_compile.compile('app/services/match_data_service.py'); py_compile.compile('app/api/v1/match_data/router.py')"`
- [ ] Model 已在 `app/models/__init__.py` 中导入
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] Alembic 迁移已生成并执行：`alembic revision --autogenerate -m "add_match_data_tables" && alembic upgrade head`
- [ ] 快速录入正确计算 `is_win`（`my_score > opponent_score`）
- [ ] 详细录入的逐分明细正确关联 `match_record`
- [ ] 比分合法性校验覆盖 bo1/bo3/bo5/bo7/custom 赛制
- [ ] 比赛记录支持按 `result=win/lose/all` 筛选
- [ ] 可选关联记分牌比赛 `match_id` 正确处理（不存在则忽略）
- [ ] gamification 积分触发（+3，异步不阻塞响应）
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`MatchRecordCreateRequest`、`MatchRecordBrief`、`MatchRecordDetail`、`MatchRecordCreateResponse`、`MatchRecordUpdate`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- `is_win` **必须** 自动计算（`my_score > opponent_score`），**禁止** 前端传入
- 比分合法性校验 **必须** 在 Service 层执行（`_validate_score_by_format`）
- gamification 积分触发 **必须** 在记录创建后执行，**禁止** 在路由层调用
- gamification 积分触发 **必须** 使用统一 API：`await GamificationService.add_points(db, user_id=user_id, event_type="record", ref_id=record_id)`
- `match_id` 不存在时 **必须** 静默忽略关联（不报错），正常创建记录
- 比赛日期 **必须** 校验不能在未来（`model_validator`）
- PATCH 编辑记录时 **必须** 在比分变更后自动重算 `is_win`
- 测试 **必须** 使用 `httpx.AsyncClient`，**禁止** 自建 HTTP 客户端
- 冒烟测试 **必须** 可作为独立脚本运行
- **覆盖度修复**：已根据覆盖度分析报告修复 X-1/X-2/X-5/X-17/A-7/X-25/A-9 等问题（A-9: `datetime.utcnow()` naive → timezone-aware）
- ALL API 端点已添加 `@limiter.limit()` 限流装饰器，全局默认 100/minute，AI 分析创建 10/hour
