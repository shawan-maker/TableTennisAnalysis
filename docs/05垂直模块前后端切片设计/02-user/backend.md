# user 模块 — 后端垂直切片设计

> **模块名称**：`user`
> **所属目录**：`app/api/v1/users/`
> **定位**：管理用户个人档案、开球网积分、打法类型、装备配置、乒乓大数据、用户注销、PIPL 数据导出
> **依据**：模块详细设计 v1.2 §2.2、API 详细设计 v1.3 §3

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.2（user 模块功能规格）
- [ ] 阅读 API 契约 §3（用户模块 8 个端点）
- [ ] 阅读 `app/models/user.py`（User 表，auth 模块已定义基础字段）
- [ ] 阅读 `app/core/deps.py`（`get_current_user` 依赖注入）
- [ ] 阅读 `app/core/response.py`（`success()` 统一响应包装）
- [ ] 阅读 `app/core/pagination.py`（`paginate()` 分页工具）
- [ ] 确认本切片范围：8 个 API 端点 + 对应 Service 方法

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 扩展 Model（User + RatingHistory + ExportTask） | `app/models/user.py` | auth #1 | ☐ |
| 2 | 定义 Schema | `app/schemas/user.py` | #1 | ☐ |
| 3 | 实现 Service | `app/services/user_service.py` | #1,#2 | ☐ |
| 4 | 实现 API 路由 | `app/api/v1/users/router.py` | #3 | ☐ |
| 5 | 注册 Router | `app/api/v1/__init__.py` | #4 | ☐ |
| 6 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #1 | ☐ |
| 7 | 编写测试 | `tests/unit/test_user.py` | #3 | ☐ |
| 8 | 编写冒烟测试 | `tests/smoke/user_smoke_test.py` | #5 | ☐ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_user.py
"""
user 模块 — 用户档案与大数据测试。
覆盖：档案获取/更新、积分更新+历史、乒乓大数据、用户注销、数据导出。
"""
import pytest
from app.core.exceptions import AppException

# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_get_profile_success(client, auth_user):
    """获取个人档案成功。"""
    resp = await client.get("/api/v1/users/profile",
                            headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "id" in data
    assert "profile" in data
    assert "profile_completeness" in data["profile"]

@pytest.mark.asyncio
async def test_update_profile_success(client, auth_user):
    """更新个人档案成功，返回完整度和新字段列表。"""
    resp = await client.patch("/api/v1/users/profile",
                              headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                              json={
                                  "playing_style": "loop",
                                  "self_assessed_level": "intermediate",
                                  "equipment_config": {
                                      "blade": {"brand": "蝴蝶", "model": "Viscaria"},
                                  },
                              })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "profile_completeness" in data
    assert "updated_fields" in data
    assert "playing_style" in data["updated_fields"]

@pytest.mark.asyncio
async def test_update_rating_success(client, auth_user):
    """更新积分成功，旧积分自动写入历史记录。"""
    # 先设置一个初始积分
    resp = await client.patch("/api/v1/users/rating",
                              headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                              json={"rating": 1550, "source": "manual"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "old_rating" in data
    assert "new_rating" in data
    assert data["new_rating"] == 1550
    assert "history_id" in data

# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_update_profile_invalid_playing_style(client, auth_user):
    """打法类型不在枚举中返回 422。"""
    resp = await client.patch("/api/v1/users/profile",
                               headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                               json={"playing_style": "invalid_style"})
    assert resp.status_code == 422
    assert "打法类型" in resp.json()["message"]

@pytest.mark.asyncio
async def test_update_rating_out_of_range(client, auth_user):
    """积分超出合理范围返回 400。"""
    resp = await client.patch("/api/v1/users/rating",
                              headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                              json={"rating": 400, "source": "manual"})
    assert resp.status_code == 400
    assert "合理范围" in resp.json()["message"]

# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_get_profile_without_token(client):
    """未携带 JWT 返回 401。"""
    resp = await client.get("/api/v1/users/profile")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_delete_account_wrong_confirmation(client, auth_user):
    """confirmation 不匹配返回 422。"""
    resp = await client.delete("/api/v1/users/account",
                               headers={"Authorization": f"Bearer {auth_user['access_token']}"},
                               json={"reason": "不再使用", "confirmation": "WRONG"})
    assert resp.status_code == 422

# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_rating_history_pagination(client, auth_user):
    """积分历史记录支持分页查询。"""
    # 先更新几次积分
    headers = {"Authorization": f"Bearer {auth_user['access_token']}"}
    for rating in [1500, 1520, 1550]:
        await client.patch("/api/v1/users/rating", headers=headers,
                            json={"rating": rating, "source": "manual"})

    resp = await client.get("/api/v1/users/rating-history?page=1&page_size=10",
                            headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3
    assert len(data["items"]) >= 3
    assert "recorded_at" in data["items"][0]
    assert "rating" in data["items"][0]

@pytest.mark.asyncio
async def test_account_deletion_cooldown(client, auth_user):
    """重复提交注销返回 409。"""
    headers = {"Authorization": f"Bearer {auth_user['access_token']}"}
    # 第一次提交
    resp1 = await client.delete("/api/v1/users/account", headers=headers,
                                json={"reason": "不再使用",
                                      "confirmation": "DELETE_ACCOUNT_CONFIRM"})
    assert resp1.status_code == 200
    # 第二次提交 → 409
    resp2 = await client.delete("/api/v1/users/account", headers=headers,
                                json={"reason": "不再使用",
                                      "confirmation": "DELETE_ACCOUNT_CONFIRM"})
    assert resp2.status_code == 409
    assert "已提交" in resp2.json()["message"]

@pytest.mark.asyncio
async def test_export_data_monthly_limit(client, auth_user):
    """同月内重复导出返回 429。"""
    headers = {"Authorization": f"Bearer {auth_user['access_token']}"}
    resp1 = await client.post("/api/v1/users/export-data", headers=headers)
    assert resp1.status_code == 200
    resp2 = await client.post("/api/v1/users/export-data", headers=headers)
    assert resp2.status_code == 429
    assert "本月" in resp2.json()["message"]
```

---

## 3. Model 实现

auth 模块已定义 `User` 基础字段（id, openid, phone, nickname, avatar_url, status, kqs_rating 等）。user 模块在此基础扩展：

```python
# app/models/user.py（在 auth 已有基础上扩展）
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import app.models  # noqa: F401  确保模型注册

from app.core.database import Base


class User(Base):
    """用户表 — auth 模块已定义基础字段，此处补充档案字段。"""
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/pending_deletion/deleted

    # --- 档案字段（user 模块扩展） ---
    kqs_rating: Mapped[int | None] = mapped_column(Integer)
    kqs_username: Mapped[str | None] = mapped_column(String(64))
    playing_style: Mapped[str | None] = mapped_column(String(32), nullable=True)  # fast_attack / loop / chop / all_round
    self_assessed_level: Mapped[str | None] = mapped_column(String(32))  # beginner/intermediate/advanced
    equipment_config: Mapped[dict | None] = mapped_column(JSONB)  # JSONB: blade/rubber_fh/rubber_bh/shoes

    # --- 注销相关 ---
    scheduled_deletion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # --- 档案完整度 ---
    profile_completeness: Mapped[int] = mapped_column(Integer, default=0)

    # --- 关联 ---
    rating_histories: Mapped[list["RatingHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    export_tasks: Mapped[list["ExportTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RatingHistory(Base):
    """积分历史记录表。"""
    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-6: 移除冗余 index=True（__table_args__ idx_rating_history_user_date 已覆盖）
    rating: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/kqs_api/tournament
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_rating_history_user_date", "user_id", "recorded_at"),
    )

    user: Mapped["User"] = relationship(back_populates="rating_histories")


class ExportTask(Base):
    """个人数据导出任务表。"""
    __tablename__ = "export_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R19-P3-6: 移除冗余 index=True（__table_args__ idx_export_user_created 已覆盖）
    task_id: Mapped[str] = mapped_column(String(64), unique=True)  # R19-P3-6: 移除冗余 index=True（unique=True 已隐式索引）；export_yyyymmdd_xxx
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/completed/failed
    download_url: Mapped[str | None] = mapped_column(String(512))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_export_user_created", "user_id", "created_at"),
    )

    user: Mapped["User"] = relationship(back_populates="export_tasks")
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入 `User`、`RatingHistory`、`ExportTask`
- [ ] 运行 `alembic revision --autogenerate -m "add_user_profile_fields_and_rating_history"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/user.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime

# --- 请求 Schema ---

class ProfileUpdateRequest(BaseModel):
    """更新个人档案请求（PATCH 语义，仅更新传入字段）。"""
    playing_style: Optional[str] = Field(default=None, description="打法类型: loop/fast_attack/chop/all_round")
    self_assessed_level: Optional[str] = Field(default=None, description="自评水平: beginner/intermediate/advanced")
    equipment_config: Optional[dict[str, Any]] = Field(default=None, description="装备配置 JSON")

    @field_validator("playing_style")
    @classmethod
    def validate_playing_style(cls, v):
        if v is not None and v not in ("loop", "fast_attack", "chop", "all_round"):
            raise ValueError("打法类型不合法")
        return v

    @field_validator("self_assessed_level")
    @classmethod
    def validate_self_level(cls, v):
        if v is not None and v not in ("beginner", "intermediate", "advanced"):
            raise ValueError("自评水平不合法")
        return v


class RatingUpdateRequest(BaseModel):
    """更新开球网积分请求。"""
    rating: int = Field(..., ge=500, le=3000, description="积分值 (500-3000)")
    kqs_username: Optional[str] = Field(default=None, max_length=128)
    source: str = Field(default="manual", description="来源: manual/kqs_api/tournament")


class AccountDeletionRequest(BaseModel):
    """用户注销请求。"""
    reason: Optional[str] = Field(default=None, max_length=500)
    confirmation: str = Field(..., description="必须为 'DELETE_ACCOUNT_CONFIRM'")


# --- 响应 Schema ---

class UserProfileResponse(BaseModel):
    """个人档案响应。"""
    id: int
    nickname: str
    avatar_url: Optional[str] = None
    profile: dict  # {kqs_rating, kqs_username, playing_style, self_assessed_level, equipment_config, profile_completeness}
    model_config = {"from_attributes": True}


class ProfileUpdateResponse(BaseModel):
    """更新档案响应。"""
    id: int
    profile_completeness: int
    updated_fields: list[str]


class RatingUpdateResponse(BaseModel):
    """积分更新响应。"""
    id: int
    old_rating: Optional[int]
    new_rating: int
    history_id: int


class RatingHistoryItem(BaseModel):
    """积分历史记录项。"""
    id: int
    rating: int
    source: str
    recorded_at: datetime
    model_config = {"from_attributes": True}


class BigDataResponse(BaseModel):
    """乒乓大数据响应。"""
    highest_win_rating: Optional[int] = None
    win_streak: int = 0
    match_cities: int = 0
    total_opponents: int = 0
    indirect_wins: list[str] = []
    total_matches: int = 0
    win_rate: float = 0.0
    favorite_shot: Optional[str] = None


class AccountDeletionResponse(BaseModel):
    """注销申请响应。"""
    scheduled_deletion_at: datetime
    can_cancel_before: datetime


class ExportCreateResponse(BaseModel):
    """导出任务创建响应。"""
    task_id: str
    status: str  # pending


class ExportStatusResponse(BaseModel):
    """导出任务状态响应。"""
    task_id: str
    status: str  # pending/processing/completed/failed
    download_url: Optional[str] = None
    expire_at: Optional[datetime] = None
    file_size: Optional[int] = None


# --- 分页包装 ---
class PaginatedRatingHistory(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RatingHistoryItem]
```

---

## 5. Service 实现

```python
# app/services/user_service.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.user import User, RatingHistory, ExportTask
from app.schemas.user import (
    ProfileUpdateRequest, RatingUpdateRequest, AccountDeletionRequest,
    UserProfileResponse, ProfileUpdateResponse, RatingUpdateResponse,
    BigDataResponse, AccountDeletionResponse,
    ExportCreateResponse, ExportStatusResponse,
    PaginatedRatingHistory, RatingHistoryItem,
)

# 应填字段（用于计算档案完整度）
PROFILE_REQUIRED_FIELDS = ["nickname", "avatar_url", "kqs_rating", "playing_style", "equipment_config"]

# 预置名人 ID 列表（间接胜利算法匹配目标）
CELEBRITY_IDS = [1, 2, 3, 4, 5]  # 马龙、孙颖莎等，实际从配置读取


class UserService:
    """用户业务逻辑层。"""

    DELETION_COOLDOWN_HOURS = 72       # 注销冷静期 72 小时
    BIG_DATA_CACHE_TTL = 86400         # 乒乓大数据缓存 24 小时
    EXPORT_LINK_TTL_DAYS = 7          # 导出链接 7 天有效
    EXPORT_MONTHLY_LIMIT = 1          # 每月限 1 次导出

    @staticmethod
    def _calculate_completeness(user: User) -> int:
        """计算档案完整度 = 已填字段数 / 应填字段数 × 100%。"""
        filled = sum(1 for f in PROFILE_REQUIRED_FIELDS if getattr(user, f, None) is not None)
        return int(filled / len(PROFILE_REQUIRED_FIELDS) * 100)

    @staticmethod
    async def get_profile(user: User, db: AsyncSession) -> UserProfileResponse:
        """获取个人档案。"""
        completeness = UserService._calculate_completeness(user)
        return UserProfileResponse(
            id=user.id,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
            profile={
                "kqs_rating": user.kqs_rating,
                "kqs_username": user.kqs_username,
                "playing_style": user.playing_style,
                "self_assessed_level": user.self_assessed_level,
                "equipment_config": user.equipment_config,
                "profile_completeness": completeness,
            },
        )

    @staticmethod
    async def update_profile(user: User, req: ProfileUpdateRequest, db: AsyncSession) -> ProfileUpdateResponse:
        """更新个人档案（PATCH 语义，仅更新传入字段）。"""
        updated_fields: list[str] = []
        if req.playing_style is not None:
            user.playing_style = req.playing_style
            updated_fields.append("playing_style")
        if req.self_assessed_level is not None:
            user.self_assessed_level = req.self_assessed_level
            updated_fields.append("self_assessed_level")
        if req.equipment_config is not None:
            user.equipment_config = req.equipment_config
            updated_fields.append("equipment_config")

        await db.commit()
        await db.refresh(user)

        completeness = UserService._calculate_completeness(user)
        return ProfileUpdateResponse(
            id=user.id,
            profile_completeness=completeness,
            updated_fields=updated_fields,
        )

    @staticmethod
    async def update_rating(user: User, req: RatingUpdateRequest, db: AsyncSession) -> RatingUpdateResponse:
        """更新开球网积分，旧积分自动写入历史记录。"""
        old_rating = user.kqs_rating

        # 创建历史记录
        if old_rating is not None:
            history = RatingHistory(
                user_id=user.id,
                rating=old_rating,
                source=req.source,
            )
            db.add(history)
            await db.flush()  # 获取 history.id
            history_id = history.id
        else:
            history_id = 0

        # 更新积分
        user.kqs_rating = req.rating
        if req.kqs_username:
            user.kqs_username = req.kqs_username
        await db.commit()
        await db.refresh(user)

        return RatingUpdateResponse(
            id=user.id,
            old_rating=old_rating,
            new_rating=req.rating,
            history_id=history_id,
        )

    @staticmethod
    async def get_rating_history(user: User, page: int, page_size: int, db: AsyncSession) -> PaginatedRatingHistory:
        """积分历史记录分页查询。"""
        offset = (page - 1) * page_size
        # 查询总数
        count_stmt = select(func.count()).select_from(RatingHistory).where(RatingHistory.user_id == user.id)
        total = (await db.execute(count_stmt)).scalar() or 0

        # 查询列表
        list_stmt = (
            select(RatingHistory)
            .where(RatingHistory.user_id == user.id)
            .order_by(RatingHistory.recorded_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(list_stmt)).scalars().all()

        return PaginatedRatingHistory(
            total=total,
            page=page,
            page_size=page_size,
            items=[RatingHistoryItem.model_validate(r) for r in rows],
        )

    @staticmethod
    async def get_big_data(user: User, db: AsyncSession) -> BigDataResponse:
        """乒乓大数据（间接胜利算法，24h 缓存）。"""
        redis = await get_redis()
        cache_key = f"big_data:user:{user.id}"

        # 尝试读取缓存
        import json
        cached = await redis.get(cache_key)
        if cached:
            return BigDataResponse(**json.loads(cached))

        # 缓存未命中 → 实时计算（限制最近 50 场比赛）
        # 实际实现中需要查询 match_record 表聚合计算
        # 此处给出简化实现框架
        from app.models.match import MatchRecord  # 延迟导入

        # 统计总比赛数和胜率
        match_count_stmt = select(
            func.count().label("total"),
            func.sum(func.cast(MatchRecord.is_win, Integer)).label("wins"),
        ).where(MatchRecord.user_id == user.id)
        match_stats = (await db.execute(match_count_stmt)).one()
        total_matches = match_stats.total or 0
        wins = match_stats.wins or 0
        win_rate = wins / total_matches if total_matches > 0 else 0.0

        # 统计对手人数（DISTINCT opponent_name）
        opp_stmt = select(func.count(func.distinct(MatchRecord.opponent_name))).where(MatchRecord.user_id == user.id)
        total_opponents = (await db.execute(opp_stmt)).scalar() or 0

        # 战胜的最高积分对手
        highest_stmt = (
            select(func.max(MatchRecord.opponent_rating))
            .where(MatchRecord.user_id == user.id, MatchRecord.is_win.is_(True))
        )
        highest_win_rating = (await db.execute(highest_stmt)).scalar()

        # 连胜场次数
        # 简化：查询最近连续胜利的场次
        recent_stmt = (
            select(MatchRecord.is_win)
            .where(MatchRecord.user_id == user.id)
            .order_by(MatchRecord.match_date.desc())
            .limit(100)
        )
        recent_results = [r[0] for r in (await db.execute(recent_stmt)).all()]
        win_streak = 0
        for r in recent_results:
            if r:
                win_streak += 1
            else:
                break

        # 间接胜利算法（BFS，最大 4 层）
        indirect_wins = await UserService._compute_indirect_wins(user.id, db)

        # 最常用技术动作（从分析报告中聚合）
        favorite_shot = None  # 实际从 analysis_report.result_data 聚合

        result = BigDataResponse(
            highest_win_rating=highest_win_rating,
            win_streak=win_streak,
            match_cities=0,  # 需要从 match_record.match_city 聚合
            total_opponents=total_opponents,
            indirect_wins=indirect_wins,
            total_matches=total_matches,
            win_rate=round(win_rate, 2),
            favorite_shot=favorite_shot,
        )

        # 回填缓存
        await redis.setex(cache_key, UserService.BIG_DATA_CACHE_TTL, json.dumps(result.model_dump()))
        return result

    @staticmethod
    async def _compute_indirect_wins(user_id: int, db: AsyncSession) -> list[str]:
        """
        间接胜利算法：从用户出发沿胜利边 BFS（最大 4 层），匹配预置名人列表。

        OPT-12 优化建议：当前实现逐层查询数据库（每层一次 SELECT），
        用户量大时性能下降。建议后续优化为递归 CTE 单次查询：

            WITH RECURSIVE indirect_wins AS (
                SELECT opponent_user_id, opponent_name, 1 AS depth
                FROM match_record
                WHERE user_id = {user_id} AND is_win = true
                UNION ALL
                SELECT m.opponent_user_id, m.opponent_name, iw.depth + 1
                FROM match_record m
                JOIN indirect_wins iw ON m.user_id = iw.opponent_user_id
                WHERE m.is_win = true AND iw.depth < 4
            )
            SELECT DISTINCT opponent_name FROM indirect_wins
            WHERE opponent_user_id = ANY(%s)

        或采用架构 §12.1 的预计算方案（比赛结束后 Celery 异步 BFS + Redis 缓存）。
        当前 BFS 实现在小用户量（< 1000）下可接受，深度限制 4 层避免无限遍历。
        """
        from collections import deque
        from app.models.match import MatchRecord

        visited: set[int] = set()
        queue: deque[tuple[int, int]] = deque([(user_id, 0)])  # (user_id, depth)
        visited.add(user_id)

        celebrity_names: list[str] = []

        while queue:
            current_uid, depth = queue.popleft()
            if depth >= 4:
                continue

            # 查询 current_uid 战胜的对手
            stmt = (
                select(MatchRecord.opponent_name, MatchRecord.opponent_user_id)
                .where(MatchRecord.user_id == current_uid, MatchRecord.is_win.is_(True))
                .limit(50)
            )
            opponents = (await db.execute(stmt)).all()

            for opp_name, opp_uid in opponents:
                if opp_uid and opp_uid in CELEBRITY_IDS and opp_name not in celebrity_names:
                    celebrity_names.append(opp_name)
                if opp_uid and opp_uid not in visited:
                    visited.add(opp_uid)
                    queue.append((opp_uid, depth + 1))

        return celebrity_names

    @staticmethod
    async def delete_account(user: User, req: AccountDeletionRequest, db: AsyncSession) -> AccountDeletionResponse:
        """用户注销（72h 冷静期）。"""
        if user.status == "pending_deletion":
            raise AppException("您已提交注销申请", 409)

        now = datetime.now(timezone.utc)
        scheduled_at = now + timedelta(hours=UserService.DELETION_COOLDOWN_HOURS)

        user.status = "pending_deletion"
        user.scheduled_deletion_at = scheduled_at
        user.deletion_reason = req.reason
        await db.commit()

        # 投递 Celery 延迟任务（72h 后执行永久删除）
        # from app.tasks.user_tasks import permanent_delete_user
        # permanent_delete_user.apply_async(args=[user.id], eta=scheduled_at)

        return AccountDeletionResponse(
            scheduled_deletion_at=scheduled_at,
            can_cancel_before=scheduled_at,
        )

    @staticmethod
    async def cancel_deletion(user: User, db: AsyncSession) -> dict:
        """撤销用户注销申请（72h 冷静期内）。API §3.10。"""
        if user.status != "pending_deletion":
            raise AppException("无待执行的注销申请", 409)
        user.status = "active"
        user.scheduled_deletion_at = None
        user.deletion_reason = None
        await db.commit()
        return {"status": "active", "cancelled_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    async def export_data(user: User, db: AsyncSession) -> ExportCreateResponse:
        """发起个人数据导出（PIPL 数据可携带权）。"""
        redis = await get_redis()
        # 检查本月导出限制
        now = datetime.now(timezone.utc)
        month_key = f"export:count:{user.id}:{now.year}{now.month:02d}"
        count = await redis.get(month_key) or 0
        if int(count) >= UserService.EXPORT_MONTHLY_LIMIT:
            raise AppException("本月已导出过，请下月再试", 429)

        # 创建导出任务
        task_id = f"export_{now.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        export_task = ExportTask(
            user_id=user.id,
            task_id=task_id,
            status="pending",
        )
        db.add(export_task)
        await db.commit()

        # 计数 +1
        await redis.incr(month_key)
        # TTL 到月末
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        end_of_month = now.replace(day=last_day, hour=23, minute=59, second=59)
        ttl = int((end_of_month - now).total_seconds())
        await redis.expire(month_key, ttl)

        # 投递 Celery 异步任务
        # from app.tasks.user_tasks import export_user_data
        # export_user_data.delay(user.id, task_id)

        return ExportCreateResponse(task_id=task_id, status="pending")

    @staticmethod
    async def get_export_status(user: User, task_id: str, db: AsyncSession) -> ExportStatusResponse:
        """查询导出任务状态。"""
        stmt = select(ExportTask).where(
            ExportTask.task_id == task_id,
            ExportTask.user_id == user.id,
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if not task:
            raise AppException("导出任务不存在", 404)

        if task.status in ("pending", "processing"):
            raise AppException("导出任务处理中，请稍后查询", 409)

        return ExportStatusResponse(
            task_id=task.task_id,
            status=task.status,
            download_url=task.download_url,
            expire_at=task.expire_at,
            file_size=task.file_size,
        )
```

---

## 6. API 路由实现

```python
# app/api/v1/users/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.response import success
from app.models.user import User
from app.schemas.user import (
    ProfileUpdateRequest, RatingUpdateRequest, AccountDeletionRequest,
)
from app.core.limiter import limiter
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["用户"])


@limiter.limit("100/minute")
@router.get("/profile", summary="获取个人档案")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.get_profile(user, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.patch("/profile", summary="更新个人档案")
async def update_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.update_profile(user, body, db)
    return success(data=data, message="档案已更新")


@limiter.limit("100/minute")
@router.patch("/rating", summary="更新开球网积分")
async def update_rating(
    body: RatingUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.update_rating(user, body, db)
    return success(data=data, message="积分已更新")


@limiter.limit("100/minute")
@router.get("/rating-history", summary="积分历史记录")
async def get_rating_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.get_rating_history(user, page, page_size, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/big-data", summary="乒乓大数据（趣味统计）")
async def get_big_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.get_big_data(user, db)
    return success(data=data)


@limiter.limit("100/minute")
@router.delete("/account", summary="用户注销（72h 冷静期）")
async def delete_account(
    body: AccountDeletionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.delete_account(user, body, db)
    return success(data=data, message="注销申请已提交，72 小时内可撤销")


@limiter.limit("100/minute")
@router.post("/account/cancel-deletion", summary="撤销注销申请（72h 冷静期内）")
async def cancel_deletion(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.cancel_deletion(user, db)
    return success(data=data, message="注销已撤销，账号恢复正常")


@limiter.limit("100/minute")
@router.post("/export-data", summary="发起个人数据导出（PIPL）")
async def export_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.export_data(user, db)
    return success(data=data, message="导出任务已创建，完成后将通过通知告知您")


@limiter.limit("100/minute")
@router.get("/export-data/{task_id}", summary="查询导出状态 + 下载链接")
async def get_export_status(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService.get_export_status(user, task_id, db)
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.users.router import router as users_router
api_router.include_router(users_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/user_smoke_test.py
"""
user 模块冒烟测试。
用法: python -m tests.smoke.user_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 0. 先登录获取 token
        print("0. Testing login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "冒烟测试用户",
        })
        if resp.status_code != 200:
            print(f"   ✗ Login failed (expected without real wx code): {resp.status_code}")
            return

        token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # 1. 获取个人档案
        print("1. Testing GET /users/profile...")
        resp = await client.get("/users/profile", headers=h)
        assert resp.status_code == 200, f"Get profile failed: {resp.text}"
        print(f"   ✓ Profile: completeness={resp.json()['data']['profile']['profile_completeness']}%")

        # 2. 更新个人档案
        print("2. Testing PATCH /users/profile...")
        resp = await client.patch("/users/profile", headers=h, json={
            "playing_style": "loop",
            "self_assessed_level": "intermediate",
            "equipment_config": {
                "blade": {"brand": "蝴蝶", "model": "Viscaria"},
            },
        })
        assert resp.status_code == 200, f"Update profile failed: {resp.text}"
        print(f"   ✓ Updated: fields={resp.json()['data']['updated_fields']}")

        # 3. 更新积分
        print("3. Testing PATCH /users/rating...")
        resp = await client.patch("/users/rating", headers=h, json={
            "rating": 1550, "source": "manual",
        })
        assert resp.status_code == 200, f"Update rating failed: {resp.text}"
        print(f"   ✓ Rating updated: {resp.json()['data']['old_rating']} -> {resp.json()['data']['new_rating']}")

        # 4. 积分历史
        print("4. Testing GET /users/rating-history...")
        resp = await client.get("/users/rating-history?page=1&page_size=10", headers=h)
        assert resp.status_code == 200, f"Rating history failed: {resp.text}"
        print(f"   ✓ History: {resp.json()['data']['total']} records")

        # 5. 乒乓大数据
        print("5. Testing GET /users/big-data...")
        resp = await client.get("/users/big-data", headers=h)
        assert resp.status_code == 200, f"Big data failed: {resp.text}"
        print(f"   ✓ Big data: total_matches={resp.json()['data']['total_matches']}")

        # 6. 发起数据导出
        print("6. Testing POST /users/export-data...")
        resp = await client.post("/users/export-data", headers=h)
        assert resp.status_code == 200, f"Export data failed: {resp.text}"
        task_id = resp.json()["data"]["task_id"]
        print(f"   ✓ Export task: {task_id}")

        # 7. 查询导出状态
        print("7. Testing GET /users/export-data/{task_id}...")
        resp = await client.get(f"/users/export-data/{task_id}", headers=h)
        # 可能返回 200 或 409（处理中）
        assert resp.status_code in (200, 409), f"Export status failed: {resp.text}"
        print(f"   ✓ Export status: {resp.json().get('data', {}).get('status', 'processing')}")

    print("\nuser_smoke_test: ALL PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_user.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.user_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导入（User, RatingHistory, ExportTask）
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] Alembic 迁移已生成并执行
- [ ] 档案完整度计算正确（5 个应填字段）
- [ ] 积分更新时旧积分自动写入 rating_history
- [ ] 乒乓大数据缓存 24h（Redis TTL）
- [ ] 用户注销设置 `pending_deletion` 状态 + `scheduled_deletion_at`
- [ ] 数据导出每月限 1 次（Redis 计数）
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`{Entity}Request`、`{Entity}Response`、`{Entity}Item`、`Paginated{Entities}`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 积分范围校验 **必须** 在 Service 层完成（500-3000），**禁止** 依赖前端校验
- 乒乓大数据 **必须** 使用 Redis 缓存（24h TTL），**禁止** 每次请求全量计算
- 用户注销 **必须** 设置 `scheduled_deletion_at = NOW() + 72h`
- 数据导出 **必须** 异步处理（Celery），**禁止** 同步阻塞返回
- 实现前 **必须** 阅读 auth 模块的完整代码（`app/models/user.py`, `app/core/deps.py`）
- ALL API 端点已添加 `@limiter.limit()` 限流装饰器，全局默认 100/minute，AI 分析创建 10/hour

### 覆盖度修复说明

- **user_profile 表合并说明**：user_profile 表在切片中合并到 User 模型中，简化一对一查询。DB 设计 v1.6 §2.2 已同步更新，标记为"已合并入 user 表"，合并字段已补入 §2.1 user 表定义
- **[X-22] 反馈历史查询端点**：GET `/video-analysis/reports/{id}/feedbacks` 端点属于 video_analysis 模块，user 切片中无需实现

---

## 9. Celery 任务

### process_account_deletions（72h 注销账户物理删除）

> 由 `beat_schedule.py` 每小时第 15 分钟触发，扫描 `status="pending_deletion"` 且 `scheduled_deletion_at < NOW()` 的用户。

```python
# app/tasks/user_tasks.py
"""用户模块 Celery 任务。"""
from datetime import datetime, timezone
from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.models.video_analysis import FileRecord, AnalysisReport
from app.models.membership import Subscription
from app.core.enums import UserStatus
from app.core.redis import get_redis_client


@shared_task(name="user.process_account_deletions")
def process_account_deletions():
    """扫描到期的注销账户，执行物理删除（匿名化个人数据）。

    每小时由 Celery Beat 触发（crontab(minute=15)）。
    流程（BR-4 七步级联）：
    1. 查询 status='pending_deletion' 且 scheduled_deletion_at < NOW() 的用户
    2. 匿名化个人数据（nickname/avatar_url/phone/openid 清空或置默认值）
    3. 关联视频标记删除（file_record.status='deleted'）
    4. 分析报告匿名化保留（analysis_report.is_anonymized=true）
    5. 取消订阅（subscription.status='cancelled'）
    6. 更新 status='deleted'
    7. 清理 Redis 缓存（用户相关 Key）
    8. 记录审计日志
    """
    db: Session = SessionLocal()
    redis = get_redis_client()

    try:
        # 1. 查询到期账户
        now = datetime.now(timezone.utc)
        stmt = select(User).where(
            User.status == UserStatus.pending_deletion,
            User.scheduled_deletion_at < now,
        )
        # R19-P3-F: 同步 Celery 任务使用 db.execute；若迁移为 async def 应改为 await db.execute 避免阻塞事件循环
        users = db.execute(stmt).scalars().all()

        if not users:
            return {"processed": 0, "message": "No pending deletions"}

        processed = 0
        for user in users:
            # 2. 匿名化个人数据
            user.nickname = "已注销用户"
            user.avatar_url = None
            user.phone = None
            user.openid = None
            user.kqs_rating = None
            user.kqs_username = None
            user.playing_style = None
            user.equipment_config = None
            user.self_assessed_level = None

            # 3. 关联视频标记删除（BR-4 级联）
            # R19-P3-F: 同步 Celery 任务使用 db.execute；若迁移为 async def 应改为 await db.execute 避免阻塞事件循环
            file_records = db.execute(
                select(FileRecord).where(FileRecord.user_id == user.id)
            ).scalars().all()
            for fr in file_records:
                fr.status = "deleted"

            # 4. 分析报告匿名化保留（BR-4 级联，保留匿名报告用于训练数据飞轮）
            # R19-P3-F: 同步 Celery 任务使用 db.execute；若迁移为 async def 应改为 await db.execute 避免阻塞事件循环
            analysis_reports = db.execute(
                select(AnalysisReport).where(AnalysisReport.user_id == user.id)
            ).scalars().all()
            for report in analysis_reports:
                report.is_anonymized = True

            # 5. 取消订阅（BR-4 级联）
            # R19-P3-F: 同步 Celery 任务使用 db.execute；若迁移为 async def 应改为 await db.execute 避免阻塞事件循环
            subscriptions = db.execute(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status.in_(["active", "expiring_soon", "cancelled"]),
                )
            ).scalars().all()
            for sub in subscriptions:
                sub.status = "cancelled"
                sub.cancelled_at = now

            # checkin_record 和 notification_record 通过 FK ondelete=CASCADE 自动删除

            # 6. 标记为已删除
            user.status = UserStatus.deleted
            user.scheduled_deletion_at = None
            user.deletion_reason = f"已物理删除，原始原因: {user.deletion_reason or 'N/A'}"

            # 7. 清理 Redis 缓存
            redis.delete(f"user:profile:{user.id}")
            redis.delete(f"user:big_data:{user.id}")
            redis.delete(f"ws:user:{user.id}")

            processed += 1

        db.commit()

        # 8. 记录审计日志（通过 admin 模块的 AuditLog）
        # admin 模块 Phase 2 实现后接入：app.tasks.audit.log_action(action="batch_delete", target_type="user", target_count=processed)

        return {"processed": processed, "message": f"Deleted {processed} accounts"}

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()
```

**实现后必须**：
- [ ] 在 `app/tasks/__init__.py` 中导入：`from app.tasks.user_tasks import process_account_deletions`
- [ ] 确认 `beat_schedule.py` 的 `autodiscover_tasks` 包含 `"app.tasks.user"`
- [ ] 在 `UserStatus` 枚举中确认 `pending_deletion` 和 `deleted` 值已定义

### export_user_data（个人数据导出异步任务）

> 由 `UserService.export_data` 投递 Celery 异步任务执行，完成后推送 WS 通知。

```python
# app/tasks/user_tasks.py（续）
from sqlalchemy.ext.asyncio import AsyncSession


@shared_task(name="user.export_user_data")
def export_user_data(user_id: int, task_id: str):
    """个人数据导出异步任务。

    流程：
    1. 查询用户所有数据（档案、积分历史、比赛记录、分析报告等）
    2. 打包为 JSON/ZIP 文件
    3. 上传至 OSS，生成下载链接
    4. 更新 ExportTask 状态为 completed
    5. WS 推送导出完成通知
    """
    import asyncio
    asyncio.run(_export_user_data_async(user_id, task_id))


async def _export_user_data_async(user_id: int, task_id: str):
    """导出任务异步实现。"""
    from app.core.database import get_async_session
    from app.services.notification_service import NotificationService
    from app.models.user import ExportTask
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta

    async with get_async_session() as db:
        # 查询导出任务
        task = (await db.execute(
            select(ExportTask).where(
                ExportTask.task_id == task_id,
                ExportTask.user_id == user_id,
            )
        )).scalar_one_or_none()

        if not task:
            return

        try:
            # 更新状态为处理中
            task.status = "processing"
            await db.commit()

            # TODO: 实际导出逻辑——查询用户数据、打包、上传 OSS
            # 简化实现：生成下载 URL
            download_url = f"https://oss.pingpongai.com/exports/{task_id}.zip"
            file_size = 0  # 实际文件大小

            # 更新任务状态为完成
            task.status = "completed"
            task.download_url = download_url
            task.file_size = file_size
            task.expire_at = datetime.now(timezone.utc) + timedelta(days=7)
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # WS 推送导出完成通知
            await NotificationService.push_ws_message(
                user_id, "export_completed", {"task_id": task.id}
            )

        except Exception as e:
            task.status = "failed"
            await db.commit()
            import logging
            logging.getLogger(__name__).error(
                "export_user_data_failed", user_id=user_id, task_id=task_id, error=str(e)
            )
```

**实现后必须**：
- [ ] 在 `app/tasks/__init__.py` 中导入：`from app.tasks.user_tasks import export_user_data`
- [ ] 在 `UserService.export_data` 中取消注释 Celery 任务投递：
      `export_user_data.delay(user.id, task_id)`

### cleanup_old_export_tasks（导出任务记录清理）

> 由 `beat_schedule.py` 每日 03:00 触发，清理 90 天前已完成的导出任务记录（DB 记录 + OSS 临时文件）。

```python
# app/tasks/user_tasks.py（续）
from datetime import timedelta


@shared_task(name="export.cleanup_old_tasks")
def cleanup_old_export_tasks():
    """清理 90 天前已完成的导出任务记录。

    每日 03:00 由 Celery Beat 触发（crontab(minute=0, hour=3)）。
    流程：
    1. 查询 status in ('completed', 'failed') 且 created_at < now() - 90d 的 ExportTask
    2. 删除 OSS 上的导出文件（如有 download_url）
    3. 删除 DB 记录
    4. 幂等设计：基于 WHERE 条件清理，重复执行无副作用

    Beat 注册：见 beat_schedule.py 中 "export-cleanup-old-tasks" 条目。
    """
    db: Session = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        stmt = select(ExportTask).where(
            ExportTask.status.in_(["completed", "failed"]),
            ExportTask.created_at < cutoff,
        )
        # R19-P3-F: 同步 Celery 任务使用 db.execute；若迁移为 async def 应改为 await db.execute 避免阻塞事件循环
        tasks = db.execute(stmt).scalars().all()

        deleted = 0
        for task in tasks:
            # 删除 OSS 上的导出文件（如有）
            if task.download_url:
                # from app.services.oss_service import OSSService
                # await OSSService.delete_file(task.download_url)
                pass  # OSS 删除在实现阶段接入
            db.delete(task)
            deleted += 1

        db.commit()
        return {"deleted": deleted, "message": f"Cleaned {deleted} old export tasks"}

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**实现后必须**：
- [ ] 在 `app/tasks/__init__.py` 中导入：`from app.tasks.user_tasks import cleanup_old_export_tasks`
- [ ] 确认 `ExportTask` 模型已从 `app.models.user` 导入
