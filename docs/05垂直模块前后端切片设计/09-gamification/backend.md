# gamification 模块 �?后端垂直切片设计

> **模块名称**：`gamification`
> **所属目�?*：`app/api/v1/gamification/`（与 `badge_system` 共用，badge 逻辑�?`badge_service.py`�?
> **定位**：训练积分、打卡日历、基础徽章、连续打卡激�?
> **依据**：模块详细设�?v1.2 §2.9、API 详细设计 v1.3 §10

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.9（gamification 模块功能规格�?
- [ ] 阅读 API 契约 §10�? 个端点：points / checkin-calendar / checkin / badges�?
- [ ] 阅读 `app/core/redis.py`（Redis 连接工具�?
- [ ] 阅读 `app/core/deps.py`（认证依赖注入）
- [ ] 确认本切片范围：4 �?API 端点 + 对应 Service 方法 + Redis 连续打卡逻辑

### 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/gamification.py` | �?| �?|
| 2 | 注册 Model | `app/models/__init__.py` | #1 | �?|
| 3 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #2 | �?|
| 4 | 定义 Schema | `app/schemas/gamification.py` | #1 | �?|
| 5 | 实现 GamificationService | `app/services/gamification_service.py` | #2,#4 | �?|
| 6 | 实现 BadgeService | `app/services/badge_service.py` | #2,#4 | �?|
| 7 | 实现 API 路由 | `app/api/v1/gamification/router.py` | #5,#6 | �?|
| 8 | 注册 Router | `app/api/v1/__init__.py` | #7 | �?|
| 9 | 编写单元测试 | `tests/unit/test_gamification.py` | #5 | �?|
| 10 | 编写冒烟测试 | `tests/smoke/gamification_smoke_test.py` | #7 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_gamification.py
"""
gamification 模块 �?积分/打卡/徽章测试�?
覆盖：训练积分获取、每日打卡、连续打卡计算、徽章解锁条件�?
"""
import pytest
from datetime import date, datetime, timedelta, timezone  # R17-P3: 补充 datetime, timezone 以支持 CST 日期
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException

@pytest.fixture
async def db_session():
    """创建测试数据库会话�?""
    ...

@pytest.fixture
async def test_user(db_session):
    """创建测试用户�?""
    from app.models.user import User
    user = User(openid="test_openid_gam", nickname="积分测试用户")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_get_points_success(client, auth_headers):
    """查询训练积分成功，返回总积�?月度积分+连续天数�?""
    resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_points" in data
    assert "monthly_points" in data
    assert "current_streak" in data
    assert "streak_icon" in data

@pytest.mark.asyncio
async def test_checkin_first_time(client, auth_headers, db_session, test_user):
    """首次打卡成功，返回积�?连续天数1�?""
    resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["points_earned"] == 2
    assert data["current_streak"] == 1

@pytest.mark.asyncio
async def test_checkin_streak_7_days_bonus(client, auth_headers, db_session):
    """连续打卡�?7 天，触发 +20 额外奖励�?""
    # 预置：前 6 天已打卡（通过 Service 直接插入�?
    from app.services.gamification_service import GamificationService
    user_id = 1  # test_user
    for i in range(6):
        d = datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=6 - i)  # R17-P3: CST 日期，避免 UTC 午夜测试 flakiness
        await GamificationService._insert_checkin_for_test(user_id, d)
    # �?7 天打�?
    resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["points_earned"] == 2  # 基础打卡积分
    assert data["current_streak"] == 7
    assert data["bonus"] == 20  # 连续7天额外奖�?

# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_checkin_calendar_invalid_month(client, auth_headers):
    """月份参数超出范围返回 422�?""
    resp = await client.get(
        "/api/v1/gamification/checkin-calendar?year=2026&month=13",
        headers=auth_headers,
    )
    assert resp.status_code == 422

# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_get_points_without_token(client):
    """未携�?JWT 返回 401�?""
    resp = await client.get("/api/v1/gamification/points")
    assert resp.status_code == 401

# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_checkin_twice_same_day(client, auth_headers):
    """同一天重复打卡返�?409�?""
    # 第一次打�?
    resp1 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp1.status_code == 200
    # 第二次打�?
    resp2 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp2.status_code == 409
    assert "今日已打�? in resp2.json()["message"]

@pytest.mark.asyncio
async def test_streak_reset_after_gap(client, auth_headers, db_session):
    """连续打卡中断后重置为1�?""
    from app.services.gamification_service import GamificationService
    user_id = 1
    # 前天打卡（间�?天）
    await GamificationService._insert_checkin_for_test(
        user_id, datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=2)  # R17-P3: CST 日期
    )
    # 今天打卡（间�?1天，应重置为1�?
    resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["current_streak"] == 1

@pytest.mark.asyncio
async def test_badge_unlock_on_streak_7(client, auth_headers, db_session):
    """连续打卡7天后，徽�?streak_7 自动解锁�?""
    from app.services.gamification_service import GamificationService
    from app.services.badge_service import BadgeService
    user_id = 1
    for i in range(6):
        d = datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=6 - i)  # R17-P3: CST 日期，避免 UTC 午夜测试 flakiness
        await GamificationService._insert_checkin_for_test(user_id, d)
    # �?天打�?�?触发徽章检�?
    await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    # 查询徽章
    resp = await client.get("/api/v1/gamification/badges", headers=auth_headers)
    data = resp.json()["data"]
    earned_ids = [b["badge_id"] for b in data["earned"]]
    assert "streak_7" in earned_ids
```

---

## 3. Model（SQLAlchemy 2.0 async�?

```python
# app/models/gamification.py
"""gamification 模块 �?训练积分、打卡记录、徽章定义、用户徽章�?""
from datetime import datetime, timezone

from sqlalchemy import String, Integer, BigInteger, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class UserPoints(Base):
    """用户积分汇总表（一对一）�?""
    __tablename__ = "user_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    total_points: Mapped[int] = mapped_column(Integer, default=0, comment="总积�?)
    monthly_points: Mapped[int] = mapped_column(Integer, default=0, comment="月度积分，每月重�?)
    bonus_points: Mapped[int] = mapped_column(Integer, default=0, comment="额外奖励积分（连续打卡等�?)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, comment="连续打卡天数")
    last_checkin_date: Mapped[Optional[date]] = mapped_column(nullable=True, comment="上次打卡日期")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_points_user_updated", "user_id", "updated_at"),  # R18-P1-4: 补充索引（§5/§6 已定义）
    )


class CheckInRecord(Base):
    """打卡记录�?""
    __tablename__ = "checkin_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)  # R19-P3-2: 移除冗余 index=True（__table_args__ idx_checkin_user_date 已覆盖）
    checkin_date: Mapped[date] = mapped_column(nullable=False, comment="打卡日期")  # R19-P3-2: 移除冗余 index=True（uq_checkin_user_date + idx_checkin_user_date 已覆盖）
    checkin_type: Mapped[str] = mapped_column(
        String(16), default="manual",
        comment="打卡类型：manual/analysis/match（自动打卡来源）",
    )
    points_earned: Mapped[int] = mapped_column(Integer, default=2)
    bonus_points: Mapped[int] = mapped_column(Integer, default=0, comment="额外奖励积分（连续打卡等）")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date"),
        Index("idx_checkin_user_date", "user_id", "checkin_date"),  # R19-P3-2: 补充索引（DB §2.16/§5 已定义）
    )


class BadgeDefinition(Base):
    """徽章定义（预置数据，也可运营新增）�?""
    __tablename__ = "badge_definition"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="徽章ID�?first_analysis")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="徽章名称")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(16), nullable=False, comment="emoji 图标")
    category: Mapped[str] = mapped_column(String(32), default="general", comment="分类")
    condition: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment='解锁条件 JSONB：{"metric":"streak_days","operator":">=","threshold":7}',
    )
    points_reward: Mapped[int] = mapped_column(Integer, default=0, comment="解锁奖励积分")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)  # R19-P3-1: 移除冗余 index=True（__table_args__ idx_badge_definition_active 已覆盖）

    __table_args__ = (
        Index("idx_badge_definition_category", "category", "sort_order"),  # R18-P2-3: 补充 sort_order 列（§5/§3.1.4 已定义）
        Index("idx_badge_definition_active", "is_active"),
    )


class UserBadge(Base):
    """用户已获得徽章�?""
    __tablename__ = "user_badge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)  # R19-P3-3: 移除冗余 index=True（__table_args__ idx_user_badge_user 已覆盖）
    badge_id: Mapped[str] = mapped_column(String(64), ForeignKey("badge_definition.id", ondelete="RESTRICT"), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
        Index("idx_user_badge_user", "user_id"),  # R18-P2-4: 补充用户徽章列表索引（§5/§3.1.5 已定义）
    )


class BadgeProgress(Base):
    """用户徽章进度（未解锁徽章的当前进度）�?""
    __tablename__ = "badge_progress"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)  # R19-P3-4: 移除冗余 index=True（__table_args__ idx_badge_progress_user 已覆盖）
    badge_id: Mapped[str] = mapped_column(String(64), ForeignKey("badge_definition.id", ondelete="RESTRICT"), nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, default=0, comment="当前指标�?)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False, comment="目标�?)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, comment="进度百分�?)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_badge_progress"),
        Index("idx_badge_progress_user", "user_id"),  # R18-P2-5: 补充用户进度列表索引（§5/§3.1.6 已定义）
    )
```

**实现后必�?*�?
- [ ] �?`app/models/__init__.py` 中导入：`from app.models.gamification import UserPoints, CheckInRecord, BadgeDefinition, UserBadge, BadgeProgress`
- [ ] 运行 `alembic revision --autogenerate -m "add_gamification_tables"`
- [ ] 运行 `alembic upgrade head`
- [ ] 预置徽章数据（通过 Alembic data migration �?seed 脚本）：

```python
# 预置徽章定义
BADGE_SEEDS = [
    {"id": "first_analysis", "name": "首分�?, "icon": "📹", "category": "analysis",
     "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 1},
     "points_reward": 10},
    {"id": "first_match", "name": "首场比赛", "icon": "🏓", "category": "match",
     "condition": {"metric": "match_count", "operator": ">=", "threshold": 1},
     "points_reward": 10},
    {"id": "streak_7", "name": "连续7�?, "icon": "🔥", "category": "streak",
     "condition": {"metric": "streak_days", "operator": ">=", "threshold": 7},
     "points_reward": 20},
    {"id": "streak_30", "name": "连续30�?, "icon": "🌟", "category": "streak",
     "condition": {"metric": "streak_days", "operator": ">=", "threshold": 30},
     "points_reward": 100},
    {"id": "analysis_10", "name": "分析10�?, "icon": "📊", "category": "analysis",
     "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 10},
     "points_reward": 30},
    {"id": "match_50", "name": "百场对决", "icon": "🏆", "category": "match",
     "condition": {"metric": "match_count", "operator": ">=", "threshold": 50},
     "points_reward": 50},
]
```

---

## 4. Schema（Pydantic�?

```python
# app/schemas/gamification.py
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


# --- 响应 Schema ---
class PointsResponse(BaseModel):
    """训练积分响应�?""
    total_points: int
    monthly_points: int
    current_streak: int
    streak_icon: str = "🔥"

    model_config = {"from_attributes": True}


class CheckInDay(BaseModel):
    """单日打卡记录�?""
    date: date
    checked_in: bool
    type: Optional[str] = None  # analysis / match / manual

    model_config = {"from_attributes": True}


class CheckInCalendarResponse(BaseModel):
    """打卡日历响应�?""
    year: int
    month: int
    days: list[CheckInDay]
    monthly_checkin_count: int
    streak_days: int

    model_config = {"from_attributes": True}


class CheckInResponse(BaseModel):
    """打卡结果响应�?""
    points_earned: int
    current_streak: int
    bonus: Optional[int] = None

    model_config = {"from_attributes": True}


class BadgeEarned(BaseModel):
    """已获得徽章�?""
    badge_id: str
    name: str
    icon: str
    earned_at: str  # ISO date

    model_config = {"from_attributes": True}


class BadgeLocked(BaseModel):
    """未获得徽章�?""
    badge_id: str
    name: str
    icon: str
    progress: int
    target: int

    model_config = {"from_attributes": True}


class BadgeListResponse(BaseModel):
    """徽章列表响应�?""
    earned: list[BadgeEarned]
    locked: list[BadgeLocked]

    model_config = {"from_attributes": True}


# --- 内部调用说明 ---
# 其他模块通过 GamificationService.add_points(db, user_id, event_type, ref_id) 直接调用�?
# 不再需要内部调�?Schema（PointsEventRequest 已移除）�?
```

---

## 5. Service 实现（@staticmethod�?

```python
# app/services/gamification_service.py
"""gamification 业务逻辑�?�?积分获取、打卡、连续打卡计算�?""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.gamification import (
    UserPoints, CheckInRecord, BadgeDefinition, UserBadge, BadgeProgress,
)
from app.schemas.gamification import (
    PointsResponse, CheckInCalendarResponse, CheckInDay, CheckInResponse,
)
from app.services.badge_service import BadgeService
from app.services.notification_service import NotificationService


class GamificationService:
    """gamification 业务逻辑层�?""

    # 积分规则�?
    POINTS_RULES = {
        "analysis": 10,   # 完成 AI 分析
        "match": 5,        # 完成记分牌比赛
        "record": 3,       # 手动录入比赛
        "checkin": 2,      # 每日打卡
        "streak_7": 20,    # 连续打卡 7 天额外奖励
        "streak_30": 100,  # 连续打卡 30 天额外奖励
        "training_session": 5,  # Phase 2: 完成训练（训练方案跟练模式触发）
        "share": 2,      # 分享报告
        "feedback": 1,   # 提交反馈
        # 注意：badge（徽章）积分不在此表中，直接使用 BadgeDefinition.points_reward
    }

    # Redis Key 统一使用 f-string 内联构造（如 f"gamification:streak:user:{user_id}"）
    # 不再使用类常量模板 + .format()，与全项目风格保持一致

    # ===================== 公开方法 =====================

    @staticmethod
    async def get_points(db: AsyncSession, user_id: int) -> PointsResponse:
        """查询训练积分（直接读取汇总表，无 SUM 查询）�?""
        result = await db.execute(
            select(UserPoints).where(UserPoints.user_id == user_id)
        )
        points = result.scalar_one_or_none()
        if points is None:
            # 用户尚无积分记录，返回默认�?
            return PointsResponse(
                total_points=0,
                monthly_points=0,
                current_streak=0,
                streak_icon="",
            )

        # 连续打卡天数（优先用 Redis 中的实时值）
        current_streak = await GamificationService._get_streak(user_id)

        return PointsResponse(
            total_points=points.total_points,
            monthly_points=points.monthly_points,
            current_streak=current_streak,
            streak_icon="🔥" if current_streak >= 3 else "",
        )

    @staticmethod
    async def get_checkin_calendar(
        db: AsyncSession, user_id: int, year: int, month: int
    ) -> CheckInCalendarResponse:
        """获取打卡日历�?""
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)

        # 查询当月打卡记录
        result = await db.execute(
            select(CheckInRecord).where(and_(
                CheckInRecord.user_id == user_id,
                CheckInRecord.checkin_date >= month_start,
                CheckInRecord.checkin_date < month_end,
            )).order_by(CheckInRecord.checkin_date)
        )
        records = result.scalars().all()

        # 构建日期映射
        checkin_map = {r.checkin_date: r.checkin_type for r in records}

        # 生成月度日历
        days: list[CheckInDay] = []
        current = month_start
        while current < month_end:
            days.append(CheckInDay(
                date=current,
                checked_in=current in checkin_map,
                type=checkin_map.get(current),
            ))
            current += timedelta(days=1)

        monthly_count = len(records)
        streak_days = await GamificationService._get_streak(user_id)

        return CheckInCalendarResponse(
            year=year,
            month=month,
            days=days,
            monthly_checkin_count=monthly_count,
            streak_days=streak_days,
        )

    @staticmethod
    async def checkin(db: AsyncSession, user_id: int) -> CheckInResponse:
        """手动打卡（每日限1次）�?""
        today = datetime.now(timezone(timedelta(hours=8))).date()

        # 检查是否已打卡
        existing = await db.execute(
            select(CheckInRecord).where(and_(
                CheckInRecord.user_id == user_id,
                CheckInRecord.checkin_date == today,
            ))
        )
        if existing.scalar_one_or_none():
            raise AppException("今日已打�?, 409)

        # 计算连续打卡天数
        streak = await GamificationService._update_streak(user_id)

        # 写入打卡记录
        checkin = CheckInRecord(
            user_id=user_id,
            checkin_date=today,
            checkin_type="manual",
            points_earned=GamificationService.POINTS_RULES["checkin"],
        )
        db.add(checkin)

        # 写入积分变动
        await GamificationService._add_points(
            db, user_id, "checkin", GamificationService.POINTS_RULES["checkin"]
        )

        # 连续打卡额外奖励
        bonus = None
        if streak == 7:
            bonus = GamificationService.POINTS_RULES["streak_7"]
            await GamificationService._add_points(db, user_id, "streak_7", bonus)
        elif streak == 30:
            bonus = GamificationService.POINTS_RULES["streak_30"]
            await GamificationService._add_points(db, user_id, "streak_30", bonus)

        await db.commit()

        # 触发徽章检�?
        await BadgeService.check_badges(db, user_id)

        return CheckInResponse(
            points_earned=GamificationService.POINTS_RULES["checkin"],
            current_streak=streak,
            bonus=bonus,
        )

    @staticmethod
    async def add_points(
        db: AsyncSession, user_id: int, event_type: str,
        ref_id: Optional[int] = None,
    ) -> int:
        """
        供其他模块调用：积分获取入口（统一 API 签名）�?        - video_analysis 分析完成 �?event_type="analysis"
        - scoring 比赛结束 �?event_type="match"
        - match_data 录入完成 �?event_type="record"
        返回本次获取的积分数�?        """
        # BL-4/F5-2: 当前为同步调用（Phase 2+ 规划事件驱动）�?        # 调用方应�?add_points 包装�?try-except 中，失败时记录日志但不阻塞业务�?        import logging
        logger = logging.getLogger(__name__)
        try:
            points = GamificationService.POINTS_RULES.get(event_type, 0)
            if points <= 0:
                return 0

            # 更新汇总表（total_points += points, monthly_points += points�?            await GamificationService._add_points(
                db, user_id, event_type, points, ref_id
            )

            # 自动打卡（分�?比赛/录入均视为当日打卡）
            await GamificationService._auto_checkin(
                db, user_id, event_type
            )

            await db.commit()

            # 触发徽章检�?            await BadgeService.check_badges(db, user_id)

            return points
        except Exception as e:
            logger.error("gamification_add_points_failed", user_id=user_id, reason=event_type, error=str(e))
            # �?re-raise，积分失败不阻塞业务
            await db.rollback()
            return 0

    @staticmethod
    async def grant_badge_points(
        db: AsyncSession, user_id: int, points: int, badge_id: str,
    ) -> None:
        """
        供 BadgeService 调用：徽章解锁奖励积分。
        - 不触发 auto_checkin / check_badges（避免递归）
        - 不查 POINTS_RULES（积分由 BadgeDefinition.points_reward 决定）
        """
        await GamificationService._add_points(
            db, user_id, "badge", points, ref_id=badge_id,
        )

    # ===================== 内部方法 =====================

    @staticmethod
    async def _get_streak(user_id: int) -> int:
        """�?Redis 读取连续打卡天数�?""
        redis = await get_redis()
        streak = await redis.get(f"gamification:streak:user:{user_id}")
        return int(streak) if streak else 0

    @staticmethod
    async def _update_streak(user_id: int) -> int:
        """
        更新连续打卡天数（Redis）�?
        规则�?
        - 相邻（昨天打卡）�?INCR
        - 间隔 1 天（前天打卡，昨天未打）�?重置�?1
        - 间隔 >1 �?�?重置�?1
        """
        redis = await get_redis()
        today = datetime.now(timezone(timedelta(hours=8))).date()
        streak_key = f"gamification:streak:user:{user_id}"
        last_date_key = f"gamification:streak:last_date:{user_id}"

        last_date_str = await redis.get(last_date_key)
        if last_date_str:
            last_date = date.fromisoformat(last_date_str)
            gap = (today - last_date).days
            if gap == 1:
                # 相邻，连�?+1
                new_streak = await redis.incr(streak_key)
            elif gap == 0:
                # 同一天（不应到达此逻辑，但兜底�?
                new_streak = int(await redis.get(streak_key) or 0)
            else:
                # 间隔 >1 天，重置�?1
                await redis.set(streak_key, 1)
                new_streak = 1
        else:
            # 首次打卡
            await redis.set(streak_key, 1)
            new_streak = 1

        # 更新最后打卡日�?
        await redis.set(last_date_key, today.isoformat())

        return new_streak

    @staticmethod
    async def _add_points(
        db: AsyncSession, user_id: int, event_type: str,
        points: int, ref_id: Optional[int] = None,
    ) -> None:
        """更新积分汇总表（total_points += points, monthly_points += points）�?""
        result = await db.execute(
            select(UserPoints).where(UserPoints.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            # 首次创建汇总记�?
            record = UserPoints(
                user_id=user_id,
                total_points=points,
                monthly_points=points,
                current_streak=0,
                last_checkin_date=None,
            )
            db.add(record)
        else:
            record.total_points += points
            record.monthly_points += points
            record.updated_at = datetime.now(timezone.utc)

    @staticmethod
    async def _auto_checkin(
        db: AsyncSession, user_id: int, source: str
    ) -> None:
        """自动打卡（分�?比赛/录入触发，如果当天尚未打卡则自动打卡）�?""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        existing = await db.execute(
            select(CheckInRecord).where(and_(
                CheckInRecord.user_id == user_id,
                CheckInRecord.checkin_date == today,
            ))
        )
        if existing.scalar_one_or_none():
            return  # 已打卡，不重�?

        # 更新连续打卡
        streak = await GamificationService._update_streak(user_id)

        checkin = CheckInRecord(
            user_id=user_id,
            checkin_date=today,
            checkin_type=source,  # analysis / match / record
            points_earned=GamificationService.POINTS_RULES["checkin"],
        )
        db.add(checkin)

        # 打卡积分
        await GamificationService._add_points(
            db, user_id, "checkin", GamificationService.POINTS_RULES["checkin"]
        )

        # 连续打卡额外奖励
        if streak == 7:
            await GamificationService._add_points(
                db, user_id, "streak_7", GamificationService.POINTS_RULES["streak_7"]
            )
        elif streak == 30:
            await GamificationService._add_points(
                db, user_id, "streak_30", GamificationService.POINTS_RULES["streak_30"]
            )

    # ===================== 测试辅助 =====================

    @staticmethod
    async def _insert_checkin_for_test(user_id: int, d: date) -> None:
        """测试专用：直接插入指定日期的打卡记录 + 更新 Redis streak�?""
        from app.core.database import get_async_session
        async with get_async_session() as db:
            checkin = CheckInRecord(
                user_id=user_id, checkin_date=d,
                checkin_type="manual",
                points_earned=GamificationService.POINTS_RULES["checkin"],
            )
            db.add(checkin)
            await db.commit()

        # 更新 Redis streak 到指定日�?
        redis = await get_redis()
        streak_key = f"gamification:streak:user:{user_id}"
        last_date_key = f"gamification:streak:last_date:{user_id}"
        current = int(await redis.get(streak_key) or 0)
        await redis.set(streak_key, current + 1)
        await redis.set(last_date_key, d.isoformat())
```

---

## 6. BadgeService（@staticmethod�?

```python
# app/services/badge_service.py
"""badge_system 业务逻辑�?�?徽章解锁检测、进度更新�?""
from datetime import datetime, timezone

from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.core.exceptions import AppException
from app.models.gamification import (
    BadgeDefinition, UserBadge, BadgeProgress,
    UserPoints, CheckInRecord,
)
from app.schemas.gamification import BadgeListResponse, BadgeEarned, BadgeLocked


class BadgeService:
    """徽章业务逻辑层�?""

    @staticmethod
    async def get_badges(db: AsyncSession, user_id: int) -> BadgeListResponse:
        """获取徽章列表（已获得/未获�?进度）�?""
        # 1. 查询所有活跃徽章定�?
        defs_result = await db.execute(
            select(BadgeDefinition)
            .where(BadgeDefinition.is_active == True)
            .order_by(BadgeDefinition.sort_order)
        )
        definitions = defs_result.scalars().all()

        # 2. 查询用户已获得徽�?
        earned_result = await db.execute(
            select(UserBadge).where(UserBadge.user_id == user_id)
        )
        earned_map = {ub.badge_id: ub for ub in earned_result.scalars().all()}

        # 3. 查询用户进度
        progress_result = await db.execute(
            select(BadgeProgress).where(BadgeProgress.user_id == user_id)
        )
        progress_map = {bp.badge_id: bp for bp in progress_result.scalars().all()}

        # 4. 聚合用户指标
        user_metrics = await BadgeService._get_user_metrics(db, user_id)

        # 5. 分类输出
        earned_list: list[BadgeEarned] = []
        locked_list: list[BadgeLocked] = []

        for definition in definitions:
            if definition.id in earned_map:
                earned_list.append(BadgeEarned(
                    badge_id=definition.id,
                    name=definition.name,
                    icon=definition.icon,
                    earned_at=earned_map[definition.id].earned_at.date().isoformat(),
                ))
            else:
                # 计算当前进度
                current_value = BadgeService._evaluate_condition(
                    definition.condition, user_metrics
                )
                target = definition.condition.get("threshold", 0)
                progress = min(current_value, target)

                locked_list.append(BadgeLocked(
                    badge_id=definition.id,
                    name=definition.name,
                    icon=definition.icon,
                    progress=progress,
                    target=target,
                ))

        return BadgeListResponse(earned=earned_list, locked=locked_list)

    @staticmethod
    async def check_badges(db: AsyncSession, user_id: int) -> None:
        """
        徽章检测触发（事件驱动）�?
        触发时机：分析完�?/ 比赛结束 / 打卡后�?
        """
        # 1. 获取所有活跃徽章定�?
        defs_result = await db.execute(
            select(BadgeDefinition).where(BadgeDefinition.is_active == True)
        )
        definitions = defs_result.scalars().all()

        # 2. 获取用户已获得徽章集�?
        earned_result = await db.execute(
            select(UserBadge.badge_id).where(UserBadge.user_id == user_id)
        )
        earned_ids = {row[0] for row in earned_result.all()}

        # 3. 聚合用户指标
        user_metrics = await BadgeService._get_user_metrics(db, user_id)

        # 4. 逐条评估未解锁徽�?
        newly_unlocked = []
        for definition in definitions:
            if definition.id in earned_ids:
                continue

            current_value = BadgeService._evaluate_condition(
                definition.condition, user_metrics
            )
            target = definition.condition.get("threshold", 0)

            if current_value >= target:
                # 解锁徽章
                user_badge = UserBadge(
                    user_id=user_id,
                    badge_id=definition.id,
                )
                db.add(user_badge)

                # 徽章奖励积分
                if definition.points_reward > 0:
                    from app.services.gamification_service import GamificationService
                    await GamificationService.grant_badge_points(
                        db, user_id, definition.points_reward, definition.id,
                    )

                # 删除进度记录（已解锁�?
                if definition.id in user_metrics:
                    pass  # progress 表清理可�?

                newly_unlocked.append(definition)
            else:
                # 更新/创建进度记录
                await BadgeService._update_progress(
                    db, user_id, definition.id, current_value, target
                )

        await db.commit()

        # 5. WS 推送徽章解�?
        if newly_unlocked:
            await BadgeService._push_badge_unlocked(user_id, newly_unlocked)

    @staticmethod
    async def _get_user_metrics(db: AsyncSession, user_id: int) -> dict:
        """聚合用户各项指标值（user_points 已改为汇总表，事件计数从 checkin_record 统计）�?""
        from sqlalchemy import func

        # 分析触发打卡次数（自动打�?checkin_type=analysis�?
        analysis_count_result = await db.execute(
            select(func.count()).select_from(CheckInRecord)
            .where(and_(
                CheckInRecord.user_id == user_id,
                CheckInRecord.checkin_type == "analysis",
            ))
        )
        analysis_count = analysis_count_result.scalar() or 0

        # 比赛/录入触发打卡次数
        match_count_result = await db.execute(
            select(func.count()).select_from(CheckInRecord)
            .where(and_(
                CheckInRecord.user_id == user_id,
                CheckInRecord.checkin_type.in_(["match", "record"]),
            ))
        )
        match_count = match_count_result.scalar() or 0

        # 连续打卡天数
        from app.services.gamification_service import GamificationService
        streak_days = await GamificationService._get_streak(user_id)

        # 总打卡天�?
        checkin_count_result = await db.execute(
            select(func.count()).select_from(CheckInRecord)
            .where(CheckInRecord.user_id == user_id)
        )
        checkin_count = checkin_count_result.scalar() or 0

        return {
            "analysis_count": analysis_count,
            "match_count": match_count,
            "streak_days": streak_days,
            "checkin_count": checkin_count,
        }

    @staticmethod
    def _evaluate_condition(condition: dict, metrics: dict) -> int:
        """
        评估徽章解锁条件 JSONB�?
        condition 格式：{"metric": "streak_days", "operator": ">=", "threshold": 7}
        """
        metric = condition.get("metric", "")
        operator = condition.get("operator", ">=")
        threshold = condition.get("threshold", 0)

        current = metrics.get(metric, 0)
        return current  # 返回当前值，由调用方判断是否满足条件

    @staticmethod
    async def _update_progress(
        db: AsyncSession, user_id: int, badge_id: str,
        current_value: int, target: int,
    ) -> None:
        """更新徽章进度�?""
        result = await db.execute(
            select(BadgeProgress).where(and_(
                BadgeProgress.user_id == user_id,
                BadgeProgress.badge_id == badge_id,
            ))
        )
        progress = result.scalar_one_or_none()

        pct = int((current_value / target * 100)) if target > 0 else 0

        if progress:
            progress.current_value = current_value
            progress.target_value = target
            progress.progress_pct = min(pct, 100)
            progress.updated_at = datetime.now(timezone.utc)
        else:
            new_progress = BadgeProgress(
                user_id=user_id,
                badge_id=badge_id,
                current_value=current_value,
                target_value=target,
                progress_pct=min(pct, 100),
            )
            db.add(new_progress)

    @staticmethod
    async def _push_badge_unlocked(user_id: int, badges: list) -> None:
        """WebSocket 推送徽章解锁通知�?""
        for badge in badges:
            await NotificationService.push_ws_message(user_id, "badge_unlocked", {
                "badge_id": badge.id,
                "name": badge.name,
                "icon": badge.icon,
                "points_reward": badge.points_reward,
            })
```

---

## 6.5 月度积分重置 Celery Task

```python
# app/tasks/gamification_beat.py
"""游戏化定时任务。"""

from datetime import datetime, timezone
from sqlalchemy import select, update
from app.core.celery import celery_app
from app.core.database import get_async_session
from app.models.gamification import UserPoints


@celery_app.task(name="gamification.reset_monthly_points")
def reset_monthly_points_task():
    """月度积分重置——每月 1 日 00:00 执行。

    规则：
    1. 归档上月积分快照（可选：写入 monthly_points_archive 表）
    2. 将所有用户的 monthly_points 重置为 0
    3. total_points 保持不变（累计积分不受影响）
    4. 幂等设计：重置操作可安全重复执行

    Beat 注册：见 beat_schedule.py 中 "gamification-monthly-points-reset" 条目。
    """
    import asyncio
    asyncio.run(_reset_monthly_points_async())


async def _reset_monthly_points_async():
    """月度积分重置异步实现。"""
    async with get_async_session() as db:
        # 批量重置 monthly_points 为 0，total_points 不变
        await db.execute(
            update(UserPoints)
            .values(monthly_points=0, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
```



---

## 7. API 路由实现（FastAPI�?

```python
# app/api/v1/gamification/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.gamification import (
    PointsResponse, CheckInCalendarResponse, CheckInResponse, BadgeListResponse,
)
from app.services.gamification_service import GamificationService
from app.services.badge_service import BadgeService

router = APIRouter(prefix="/gamification", tags=["游戏�?积分徽章"])


@limiter.limit("100/minute")
@router.get("/points", summary="训练积分")
async def get_points(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询训练积分（总积�?+ 月度积分 + 连续打卡天数）�?""
    data = await GamificationService.get_points(db, user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/checkin-calendar", summary="打卡日历（月度）")
async def get_checkin_calendar(
    year: int = Query(default=None, ge=2020, le=2100, description="年，默认当前�?),
    month: int = Query(default=None, ge=1, le=12, description="月，默认当前�?),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取月度打卡日历�?""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    data = await GamificationService.get_checkin_calendar(db, user.id, year, month)
    return success(data=data)


@limiter.limit("1/day", key_func=lambda r: r.state.user)
@router.post("/checkin", summary="手动打卡")
async def checkin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """每日手动打卡（每日限1次）�?""
    data = await GamificationService.checkin(db, user.id)
    return success(data=data, message="打卡成功")


@limiter.limit("100/minute")
@router.get("/badges", summary="徽章列表（已获得/未获得）")
async def get_badges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询徽章列表（已获得 + 未获得含进度）�?""
    data = await BadgeService.get_badges(db, user.id)
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.gamification.router import router as gamification_router
api_router.include_router(gamification_router)
```

---

## 8. 冒烟测试脚本

```python
# tests/smoke/gamification_smoke_test.py
"""
gamification 模块冒烟测试�?
用法: python -m tests.smoke.gamification_smoke_test
"""
import httpx
import asyncio
from datetime import datetime, timezone


BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("1. Testing login...")
        login_resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "gamification冒烟测试",
        })
        if login_resp.status_code != 200:
            print(f"   �?Login failed: {login_resp.status_code}")
            return
        token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("   �?Login success")

        # 2. 查询训练积分
        print("2. Testing GET /gamification/points...")
        resp = await client.get("/gamification/points", headers=headers)
        assert resp.status_code == 200, f"Points failed: {resp.text}"
        points = resp.json()["data"]
        print(f"   �?Total: {points['total_points']}, Streak: {points['current_streak']}")

        # 3. 查询打卡日历
        print("3. Testing GET /gamification/checkin-calendar...")
        now = datetime.now(timezone.utc)
        resp = await client.get(
            f"/gamification/checkin-calendar?year={now.year}&month={now.month}",
            headers=headers,
        )
        assert resp.status_code == 200, f"Calendar failed: {resp.text}"
        calendar = resp.json()["data"]
        print(f"   �?Days: {len(calendar['days'])}, Monthly checkins: {calendar['monthly_checkin_count']}")

        # 4. 手动打卡
        print("4. Testing POST /gamification/checkin...")
        resp = await client.post("/gamification/checkin", headers=headers)
        assert resp.status_code == 200, f"Checkin failed: {resp.text}"
        checkin = resp.json()["data"]
        print(f"   �?Points earned: {checkin['points_earned']}, Streak: {checkin['current_streak']}")

        # 5. 重复打卡（应返回 409�?
        print("5. Testing duplicate checkin (expect 409)...")
        resp = await client.post("/gamification/checkin", headers=headers)
        assert resp.status_code == 409, f"Duplicate checkin should fail: {resp.text}"
        print("   �?Duplicate checkin correctly rejected")

        # 6. 查询徽章列表
        print("6. Testing GET /gamification/badges...")
        resp = await client.get("/gamification/badges", headers=headers)
        assert resp.status_code == 200, f"Badges failed: {resp.text}"
        badges = resp.json()["data"]
        print(f"   �?Earned: {len(badges['earned'])}, Locked: {len(badges['locked'])}")

    print("\ngamification_smoke_test: ALL PASSED �?)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_gamification.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.gamification_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导�?
- [ ] Router 已在 `app/api/v1/__init__.py` 中注�?
- [ ] Alembic 迁移已生成并执行
- [ ] 徽章种子数据已预置（6+ 个基础徽章�?
- [ ] Redis streak 键格式正确（`gamification:streak:user:{user_id}` / `gamification:streak:last_date:{user_id}`�?
- [ ] 积分规则表完整（analysis +10 / match +5 / record +3 / checkin +2 / streak_7 +20 / streak_30 +100�?
- [ ] 连续打卡计算正确（相邻→INCR / 间隔1天→重置1 / 间隔>1天→重置1�?
- [ ] 徽章检测在打卡后正确触�?
- [ ] WS 推�?`badge_unlocked` 事件格式正确
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?
- [ ] 无废话注释、无注释掉的死代�?

---

## 反幻觉约�?

- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- Schema **必须** 遵循命名：`PointsResponse`、`CheckInResponse`、`BadgeListResponse` �?
- **禁止** �?API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- Redis streak 计算逻辑 **必须** 使用 `gamification:streak:user:{user_id}` �?`gamification:streak:last_date:{user_id}` 双键
- 徽章解锁条件 **必须** 使用 JSONB `condition` 字段（metric/operator/threshold�?
- 徽章检�?**必须** 事件驱动（分析完�?比赛结束/打卡后）�?*禁止** 轮询
- WS 推�?**必须** 使用 `ws:user:{user_id}` 频道 + `badge_unlocked` 事件类型
- 积分规则 **必须** 定义�?`POINTS_RULES` 字典中，**禁止** 硬编码散落各�?
- **注意**：badge_definition/user_badge/badge_progress 3 张表已在 DB 设计 v1.2 §3.1.4-3.1.6 中补齐（X-28 修复）。badge_definition PK �?VARCHAR(64) 语义化编码，与切片定义一致�?
- **覆盖度修�?*：已根据覆盖度分析报告修�?X-1/X-2/X-5/X-17/A-7/A-9 等问题（A-9: `datetime.utcnow()` naive �?timezone-aware�?- 所�?API 端点 **必须** 添加 `@limiter.limit("100/minute")` 限流装饰器，**禁止** 裸奔无限�?- `POST /gamification/checkin`（每日打卡）**必须** 使用 `@limiter.limit("1/day", key_func=lambda r: r.state.user)` 按用户每日限 1 次，**禁止** 使用通用限流规则
- `from app.core.limiter import limiter` **必须** 在路由文�?import 区声明，**禁止** 遗漏导入
