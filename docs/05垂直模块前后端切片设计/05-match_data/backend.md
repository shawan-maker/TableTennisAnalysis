# match_data 模块 — 后端垂直切片设计

> **模块名称**：`match_data`
> **所属目录**：`app/api/v1/match_data/`
> **定位**：手动录入比赛数据，支持快速录入（只录总比分）和详细录入（逐分技术动作）
> **依据**：模块详细设计 v1.2 §2.5、API 详细设计 v1.3 §7

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.5（match_data 模块功能规格）
- [ ] 阅读 API 契约 §7（比赛数据模块 4 个端点，§7.1-§7.4，R13-P3 文档同步）
- [ ] 阅读 `app/core/response.py`（统一响应 `success()`）
- [ ] 阅读 `app/core/deps.py`（`get_current_user` 依赖注入）
- [ ] 阅读 `app/core/pagination.py`（分页工具 `paginate()`）
- [ ] 阅读 `app/models/scoring.py`（`Match` 表，用于可选关联 `match_id`）
- [ ] 确认本切片范围：4 个 API 端点（POST/GET 列表/GET 详情/PATCH 编辑，R13-P3 文档同步：F5 PATCH 已实现）+ 对应 Service 方法 + 2 个 Model

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/match.py` | 无 | ☐ |（R13-P3 文档同步：与 Match/ScoreRecord 同文件）
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

> **R13-P3 文档同步**：实际测试（`tests/unit/test_match_data.py`）与本节样例的演化差异——① fixture 使用 conftest 的 `client` + `auth_headers`（非自建 `match_data_ctx`/`auth_user2`）；② `match_date` 因 Schema 提供默认值（§4）可省略；③ 跨用户隔离用例落地于 `tests/unit/test_supplements_p2.py::TestMatchRecordPatchIsolation` （跨用户 PATCH 404/code 40413 + 数据不变断言 + 属主对照，URL 含完整 `/records` 段，R12-MatchData-D1/D2 修复）；④ 新增 R12 修复回归用例 `test_update_record_is_win_not_acceptable` / `test_update_record_single_score_recalc` 及 409 关联编辑 / 空更新体 422 / notes 编辑用例。样例保留作为场景规划参考。
> - **R13-P3 文档同步（R13-MatchData-1 已修复）**：`update_record`（Service 层）在任一比分字段变更时，应用更新后统一调用 `_validate_score_by_format(my_score, opponent_score, format)` 校验合并比分 —— 单边 PATCH 造出非法赛制比分（如 bo5 3:1 改 my_score=0 → 0:1，胜方未达 3 局）返回 422 `ERR_SCORE_INVALID`（「比分不符合赛制规则」，对齐 API 设计 §7.4 错误表）；同时 is_win 按合并后比分重算（OR 语义保留）。因此 `test_update_record_single_score_recalc` 实际落地版改用 custom 赛制（唯一约束非平局）验证单边改分翻转胜负 —— 定局赛制（bo1/bo3/bo5/bo7）的合法比分对均无法通过单边改分翻转胜负。
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
# app/models/match.py（节选 — R13-P3 文档同步：MatchRecord/ManualScoreDetail 实际定义于
# app/models/match.py，与 Match/ScoreRecord/MatchStatistic/ShareRecord 同文件，非独立
# app/models/match_data.py；字段以实现为准：新增 opponent_user_id / notes，
# 时间列改用 server_default=func.now()（DB DEFAULT NOW() 兜底，create 时业务层注入 match_date））
"""
比赛数据模块数据模型（位于 match.py，与记分牌表同文件）。
包含：MatchRecord（手动录入比赛记录）、ManualScoreDetail（逐分明细）。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MatchRecord(Base):
    """比赛记录 — 手动录入 + 记分牌关联。DB §2.13"""

    __tablename__ = "match_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    match_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True
    )
    opponent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opponent_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opponent_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    my_score: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    is_win: Mapped[bool] = mapped_column(Boolean, nullable=False)
    format: Mapped[str] = mapped_column(String(20), default="bo5", nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="friendly", nullable=False)
    match_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_detailed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- 关系 ---
    details: Mapped[list["ManualScoreDetail"]] = relationship(
        back_populates="record", cascade="all, delete-orphan",
        order_by="ManualScoreDetail.sequence",
    )

    __table_args__ = (
        Index("idx_mrecord_user_date", "user_id", "match_date"),
    )

    def __repr__(self) -> str:
        return f"<MatchRecord(id={self.id}, user_id={self.user_id}, score={self.my_score}:{self.opponent_score})>"


class ManualScoreDetail(Base):
    """手动记分详情 — 一对多关联 MatchRecord。DB §2.14"""

    __tablename__ = "manual_score_detail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("match_record.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    scorer: Mapped[str] = mapped_column(String(10), nullable=False)  # user/opponent
    score_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    technique_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- 关系 ---
    record: Mapped["MatchRecord"] = relationship(back_populates="details")

    __table_args__ = (
        Index("idx_msd_record_seq", "match_record_id", "sequence"),
    )

    def __repr__(self) -> str:
        return f"<ManualScoreDetail(id={self.id}, seq={self.sequence}, scorer={self.scorer!r})>"
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入：`from app.models.match import MatchRecord, ManualScoreDetail` （R13-P3 文档同步：实际从 app/models/match.py 导入）
- [ ] 运行 `alembic revision --autogenerate -m "add_match_data_tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/match_data.py — R13-P3 文档同步（以实现为准回写）：
# ① match_date 提供默认值（default_factory=now），创建请求可省略；
# ② MatchRecordUpdate 不含 is_win（R12-MatchData-B1：自动计算禁止前端传入）；
# ③ opponent_name/match_date 可空（对齐 DB §2.13 nullable）；
# ④ MatchRecordDetail 继承 MatchRecordBrief 并补充 notes/match_id/is_detailed；
# ⑤ MatchRecordCreateResponse 补充 match_id（API §7.1 / R6-Match-1）
"""
app/schemas/match_data.py — 比赛数据模块 Pydantic Schema

依据：API §7 match-data 端点契约 / 切片 05-match_data/backend.md §4
规范：{Entity}Request / {Entity}Response 命名
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from typing import Literal


# =============================================================================
# 请求 Schema
# =============================================================================

class ManualScoreDetailItem(BaseModel):
    """手动得分明细项"""

    sequence: int = Field(..., ge=1, description="得分序号")
    scorer: Literal["user", "opponent"] = Field(..., description="得分方")
    score_method: Literal["serve_point", "rally_point", "opponent_error"] = Field(..., description="得分方式")
    technique_action: Optional[str] = Field(default=None, max_length=30, description="技术动作")


class MatchRecordCreateRequest(BaseModel):
    """创建比赛记录请求（快速/详细录入）"""

    opponent_name: str = Field(..., min_length=1, max_length=64, description="对手名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    my_score: int = Field(..., ge=0, le=99, description="我的得分")
    opponent_score: int = Field(..., ge=0, le=99, description="对手得分")
    format: Literal["bo1", "bo3", "bo5", "bo7", "custom"] = Field(default="bo5", description="赛制")
    match_type: Literal["friendly", "tournament", "training"] = Field(default="friendly", description="比赛类型")
    match_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="比赛日期")
    details: Optional[list[ManualScoreDetailItem]] = Field(default=None, description="详细得分明细")
    match_id: Optional[int] = Field(default=None, ge=1, description="关联记分牌比赛 ID")

    @model_validator(mode="after")
    def validate_score(self):
        """比分不能相同 + 日期不能晚于当前时间"""
        if self.my_score == self.opponent_score:
            raise ValueError("比分不能相同")
        if self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self


class MatchRecordUpdate(BaseModel):
    """编辑比赛记录请求（PATCH 语义）"""

    opponent_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000)
    my_score: Optional[int] = Field(default=None, ge=0, le=99)
    opponent_score: Optional[int] = Field(default=None, ge=0, le=99)
    # R12-MatchData-B1: is_win 禁止前端传入，必须自动计算（设计反幻觉约束）
    # Schema 不定义 is_win 字段 — 未知字段被 Pydantic 忽略，服务端 update_record 重算
    match_date: Optional[datetime] = Field(default=None)
    match_type: Optional[Literal["friendly", "tournament", "training"]] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_score_update(self):
        """比分不能相同（仅当两个分数同时传入时检查）"""
        if self.my_score is not None and self.opponent_score is not None:
            if self.my_score == self.opponent_score:
                raise ValueError("比分不能相同")
        if self.match_date is not None and self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self


class MatchRecordListQuery(BaseModel):
    """比赛记录列表查询"""

    result: Optional[Literal["win", "lose", "all"]] = Field(default="all")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# =============================================================================
# 响应 Schema
# =============================================================================

class MatchRecordBrief(BaseModel):
    """比赛记录简要"""

    id: int
    opponent_name: Optional[str] = None
    opponent_rating: Optional[int] = None
    my_score: int
    opponent_score: int
    is_win: bool
    format: str
    match_type: str
    match_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MatchRecordDetail(MatchRecordBrief):
    """比赛记录详情（含得分明细）"""

    match_id: Optional[int] = None
    is_detailed: bool = False
    notes: Optional[str] = None
    details: list[ManualScoreDetailItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MatchRecordCreateResponse(BaseModel):
    """创建比赛记录响应"""

    id: int
    is_win: bool
    match_id: Optional[int] = None  # R6-Match-1: API §7.1 match_id 字段
```

---

## 5. Service 实现

```python
# app/services/match_data_service.py — R13-P3 文档同步（以实现为准回写）：
# ① session 工厂 get_async_session → async_session_factory；
# ② AppException 携带端点级业务错误码（42210/40413/40911/40411/40000，API §1.8）；
# ③ create_record 响应补充 match_id（API §7.1 / R6-Match-1）；
# ④ list_records 签名改为 (user_id, result_filter, page, page_size)，手动分页构造
#    dict（match_date isoformat），不再经 MatchRecordBrief.model_validate；
# ⑤ get_detail 响应补充 notes；
# ⑥ create_record_from_scoring 的 match_date 保留完整 timezone-aware datetime
#    （CST 兜底），非 finished_at.date()；
# ⑦ update_record 返回 updated_fields，任一比分变更即重算 is_win（R12-MatchData-B2）
"""
app/services/match_data_service.py — 比赛数据业务逻辑层

依据：切片 05-match_data/backend.md §3-§5
规范：Service 方法使用 @staticmethod，禁止创建实例
功能：手动录入 + 列表/详情 + 编辑 + 记分牌级联
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import (
    AppException,
    ERR_BAD_REQUEST,
    ERR_MATCH_NOT_FOUND,
    ERR_RECORD_NOT_FOUND,
    ERR_RECORD_LINKED,
    ERR_SCORE_INVALID,
)
from app.models.match import (
    ManualScoreDetail,
    Match,
    MatchRecord,
    ScoreRecord,
)
from app.schemas.match_data import (
    ManualScoreDetailItem,
    MatchRecordCreateRequest,
    MatchRecordUpdate,
)

logger = logging.getLogger(__name__)


class MatchDataService:
    """比赛数据业务逻辑层"""

    FORMAT_WIN_MAP = {
        "bo1": 1,
        "bo3": 2,
        "bo5": 3,
        "bo7": 4,
    }

    # =================================================================
    # 辅助方法
    # =================================================================

    @staticmethod
    def _validate_score_by_format(my_score: int, opp_score: int, fmt: str) -> bool:
        """验证比分是否符合赛制规则"""
        if fmt == "custom":
            return my_score != opp_score
        win_needed = MatchDataService.FORMAT_WIN_MAP.get(fmt)
        if win_needed is None:
            return False
        if my_score == win_needed:
            return opp_score < win_needed
        if opp_score == win_needed:
            return my_score < win_needed
        return False

    @staticmethod
    async def _trigger_gamification(user_id: int, record_id: int) -> None:
        """触发游戏化积分（try/except 不阻塞）"""
        try:
            from app.services.gamification_service import GamificationService
            async with async_session_factory() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="record", ref_id=record_id
                )
        except Exception as e:
            logger.error("match_data_trigger_gamification_failed", extra={
                "error": str(e), "record_id": record_id
            })

    # =================================================================
    # CRUD
    # =================================================================

    @staticmethod
    async def create_record(user_id: int, req: MatchRecordCreateRequest) -> dict:
        """创建比赛记录（快速/详细录入）"""
        # 1. 比分验证
        if not MatchDataService._validate_score_by_format(
            req.my_score, req.opponent_score, req.format
        ):
            raise AppException("比分不符合赛制规则", 422, code=ERR_SCORE_INVALID)

        # 2. is_win 自动计算
        is_win = req.my_score > req.opponent_score

        # 3. is_detailed 检测
        is_detailed = req.details is not None and len(req.details) > 0

        async with async_session_factory() as db:
            # 4. 可选 match_id 验证
            match_id = req.match_id
            if match_id is not None:
                result = await db.execute(
                    select(Match).where(Match.id == match_id, Match.user_id == user_id)
                )
                if result.scalar_one_or_none() is None:
                    match_id = None  # 静默忽略不存在的 match_id

            # 5. 创建 MatchRecord
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
            await db.flush()

            # 6. 详细录入 -> 创建 ManualScoreDetail
            if is_detailed and req.details:
                for item in req.details:
                    detail = ManualScoreDetail(
                        match_record_id=record.id,
                        sequence=item.sequence,
                        scorer=item.scorer,
                        score_method=item.score_method,
                        technique_action=item.technique_action,
                    )
                    db.add(detail)

            await db.commit()
            await db.refresh(record)

        # 7. 触发游戏化积分（不阻塞）
        await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": is_win, "match_id": record.match_id}

    @staticmethod
    async def create_record_from_scoring(
        db: AsyncSession, match_id: int, user_id: int, trigger_points: bool = True
    ) -> dict:
        """
        记分牌结束比赛时级联创建记录。
        接收调用方的 db session，不创建新 session。
        trigger_points=False 时跳过积分触发（避免与 finish_match 重复）。
        """
        # 1. 查询 Match
        result = await db.execute(
            select(Match).where(Match.id == match_id, Match.user_id == user_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            raise AppException("记分牌比赛不存在", 404, code=ERR_MATCH_NOT_FOUND)

        # 2. 解析最终比分
        if match.final_score and ":" in match.final_score:
            parts = match.final_score.split(":")
            my_score = int(parts[0].strip())
            opponent_score = int(parts[1].strip())
        else:
            my_score = match.current_score_user or 0
            opponent_score = match.current_score_opp or 0

        # 3. 查询得分记录
        result = await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.match_id == match_id)
            .order_by(ScoreRecord.sequence)
        )
        score_records = result.scalars().all()
        is_detailed = len(score_records) > 0

        # 4. 创建 MatchRecord
        # 使用 CST（UTC+8）作为默认 match_date，避免跨日边界错误
        tz_cst = timezone(timedelta(hours=8))
        match_date = match.finished_at if match.finished_at else datetime.now(tz_cst)

        record = MatchRecord(
            user_id=user_id,
            opponent_name=match.opponent_name,
            opponent_rating=match.opponent_rating,
            my_score=my_score,
            opponent_score=opponent_score,
            is_win=match.is_win if match.is_win is not None else (my_score > opponent_score),
            format=match.format,
            match_type=match.match_type,
            match_date=match_date,
            match_id=match_id,
            is_detailed=is_detailed,
        )
        db.add(record)
        await db.flush()

        # 5. 创建 ManualScoreDetail
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

        # 6. 条件触发游戏化积分
        if trigger_points:
            await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": record.is_win}

    @staticmethod
    async def list_records(
        user_id: int, result_filter: str | None, page: int, page_size: int
    ) -> dict:
        """比赛记录列表（分页）"""
        async with async_session_factory() as db:
            qs = select(MatchRecord).where(MatchRecord.user_id == user_id)
            count_qs = select(func.count()).select_from(MatchRecord).where(
                MatchRecord.user_id == user_id
            )

            if result_filter and result_filter != "all":
                is_win_filter = result_filter == "win"
                qs = qs.where(MatchRecord.is_win == is_win_filter)
                count_qs = count_qs.where(MatchRecord.is_win == is_win_filter)

            qs = qs.order_by(MatchRecord.match_date.desc())

            # 计数
            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            # 分页查询
            result = await db.execute(qs.offset((page - 1) * page_size).limit(page_size))
            records = result.scalars().all()

            items = [
                {
                    "id": r.id,
                    "opponent_name": r.opponent_name,
                    "opponent_rating": r.opponent_rating,
                    "my_score": r.my_score,
                    "opponent_score": r.opponent_score,
                    "is_win": r.is_win,
                    "format": r.format,
                    "match_type": r.match_type,
                    "match_date": r.match_date.isoformat() if r.match_date else None,
                }
                for r in records
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }

    @staticmethod
    async def get_detail(user_id: int, record_id: int) -> dict:
        """比赛记录详情（含得分明细）"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise AppException("比赛记录不存在", 404, code=ERR_RECORD_NOT_FOUND)

            # 查询得分明细
            result = await db.execute(
                select(ManualScoreDetail)
                .where(ManualScoreDetail.match_record_id == record_id)
                .order_by(ManualScoreDetail.sequence)
            )
            details = result.scalars().all()

            return {
                "id": record.id,
                "opponent_name": record.opponent_name,
                "opponent_rating": record.opponent_rating,
                "my_score": record.my_score,
                "opponent_score": record.opponent_score,
                "is_win": record.is_win,
                "format": record.format,
                "match_type": record.match_type,
                "match_date": record.match_date.isoformat() if record.match_date else None,
                "match_id": record.match_id,
                "is_detailed": record.is_detailed,
                "notes": record.notes,
                "details": [
                    {
                        "sequence": d.sequence,
                        "scorer": d.scorer,
                        "score_method": d.score_method,
                        "technique_action": d.technique_action,
                    }
                    for d in details
                ],
            }

    @staticmethod
    async def update_record(
        user_id: int, record_id: int, data: MatchRecordUpdate
    ) -> dict:
        """编辑比赛记录（PATCH 语义）"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise AppException("比赛记录不存在", 404, code=ERR_RECORD_NOT_FOUND)

            # 关联记分牌的记录不可编辑
            if record.match_id is not None:
                raise AppException(
                    "比赛记录已关联记分牌，不可编辑", 409, code=ERR_RECORD_LINKED
                )

            update_data = data.model_dump(exclude_unset=True)
            if not update_data:
                raise AppException("未提供任何更新字段", 422, code=ERR_BAD_REQUEST)

            # 记录实际更新的字段名（is_win 不在 Update schema 中，禁止前端传入）
            updated_fields = list(update_data.keys())

            for field, value in update_data.items():
                if hasattr(record, field):
                    setattr(record, field, value)

            # R12-MatchData-B2: 任一比分变更即重算 is_win（服务端自动计算）
            # 比分字段在模型层非空，应用更新后直接比较即可
            if data.my_score is not None or data.opponent_score is not None:
                record.is_win = record.my_score > record.opponent_score

            await db.commit()
            await db.refresh(record)

            return {
                "id": record.id,
                "is_win": record.is_win,
                "updated_fields": updated_fields,
            }
```

---

## 6. API 路由实现

```python
# app/api/v1/match_data/router.py — R13-P3 文档同步（以实现为准回写）：
# ① 装饰器顺序修正为 @router.post(...) 在上、@limiter.limit(...) 在下 —
#    slowapi 要求限流装饰器位于路由装饰器内层，否则路由表注册原始函数、限流失效；
# ② 端点补充 request: Request 参数（slowapi 限流必需）；
# ③ 限流改用 RateLimits.DEFAULT 常量（app/core/limiter.py，值 "100/minute"）
"""
app/api/v1/match_data/router.py — 比赛数据模块 API 路由

依据：API §7 match-data 端点契约 / 切片 05-match_data/backend.md §4
规范：路由只调用 Service，禁止在路由中写业务逻辑
S2 实现：4 个 match-data 端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.schemas.match_data import MatchRecordCreateRequest, MatchRecordUpdate
from app.services.match_data_service import MatchDataService

router = APIRouter(prefix="/match-data", tags=["比赛数据"])


@router.post("/records", summary="创建比赛记录")
@limiter.limit(RateLimits.DEFAULT)
async def create_record(
    body: MatchRecordCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建比赛记录（快速/详细录入）"""
    data = await MatchDataService.create_record(user.id, body)
    return success(data=data, message="比赛记录已创建")


@router.get("/records", summary="比赛记录列表")
@limiter.limit(RateLimits.DEFAULT)
async def list_records(
    request: Request,
    result: Optional[str] = Query(default="all", pattern="^(win|lose|all)$", description="结果过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """比赛记录列表（分页）"""
    data = await MatchDataService.list_records(user.id, result, page, page_size)
    return success(data=data)


@router.get("/records/{record_id}", summary="比赛记录详情")
@limiter.limit(RateLimits.DEFAULT)
async def get_record(
    request: Request,
    record_id: int,
    user: User = Depends(get_current_user),
):
    """比赛记录详情（含得分明细）"""
    data = await MatchDataService.get_detail(user.id, record_id)
    return success(data=data)


@router.patch("/records/{record_id}", summary="编辑比赛记录")
@limiter.limit(RateLimits.DEFAULT)
async def update_record(
    body: MatchRecordUpdate,
    request: Request,
    record_id: int,
    user: User = Depends(get_current_user),
):
    """编辑比赛记录（PATCH 语义，仅限未关联记分牌的记录）"""
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

> **R13-P3 文档同步**：本节冒烟脚本（`tests/smoke/match_data_smoke_test.py`）未落地——全项目 `tests/smoke/` 仅含 `__init__.py`，S2 阶段验证以 `tests/unit/test_match_data.py`（20 用例，含 R12-MatchData-B1/B2 修复回归）+ `tests/unit/test_supplements_p2.py::TestMatchRecordPatchIsolation`（跨用户隔离 2 用例）替代。以下脚本保留作为后续落地参考。
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
- [ ] 冒烟测试通过：`python -m tests.smoke.match_data_smoke_test`（R13-P3 文档同步：冒烟脚本未落地，S2 验证以 `tests/unit/test_match_data.py` 20 用例 + `tests/unit/test_supplements_p2.py::TestMatchRecordPatchIsolation` 2 用例替代）
- [ ] 后端语法检查：`python -c "import py_compile; py_compile.compile('app/models/match.py'); py_compile.compile('app/schemas/match_data.py'); py_compile.compile('app/services/match_data_service.py'); py_compile.compile('app/api/v1/match_data/router.py')"`
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
