# membership 模块 — 后端垂直切片设计

> **模块名称**：`membership`
> **所属目录**：`app/api/v1/membership/`
> **定位**：会员等级管理、权益配置、订阅续费、免费额度控制
> **依据**：模块详细设计 v1.2 §2.10、API 详细设计 v1.3 §11

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.10（membership 模块功能规格）
- [ ] 阅读 API 契约 §11，3 个端点：tiers / current / quota
- [ ] 阅读 `app/core/redis.py`（Redis 连接工具）
- [ ] 阅读 `app/core/deps.py`（认证依赖注入 + 权限守卫）
- [ ] 确认本切片范围：3 个 API 端点 + 对应 Service 方法 + Redis 免费额度计数器

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/membership.py` | — | ✓ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ✓ |
| 3 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #2 | ✓ |
| 4 | 定义 Schema | `app/schemas/membership.py` | #1 | ✓ |
| 5 | 实现 MembershipService | `app/services/membership_service.py` | #2,#4 | ✓ |
| 6 | 实现 API 路由 | `app/api/v1/membership/router.py` | #5 | ✓ |
| 7 | 注册 Router | `app/api/v1/__init__.py` | #6 | ✓ |
| 8 | 实现 Celery Beat 到期检测任务 | `app/tasks/membership_tasks.py` | #5 | ✓ |
| 9 | 编写单元测试 | `tests/unit/test_membership.py` | #5 | ✓ |
| 10 | 编写冒烟测试 | `tests/smoke/membership_smoke_test.py` | #6 | ✓ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_membership.py
"""
membership 模块 — 会员等级、权益、额度测试。
覆盖：等级权益对比、当前会员状态、免费额度计数、到期检测。
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException

@pytest.fixture
async def db_session():
    """创建测试数据库会话。""
    ...

@pytest.fixture
async def free_user(db_session):
    """创建免费用户。""
    from app.models.user import User
    user = User(openid="test_free_openid", nickname="免费用户")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def member_user(db_session):
    """创建会员用户（带有效订阅）。""
    from app.models.user import User
    from app.models.membership import Subscription
    user = User(openid="test_member_openid", nickname="会员用户")
    db_session.add(user)
    await db_session.flush()
    sub = Subscription(
        user_id=user.id,
        tier="member",
        status="active",
        start_at=datetime.now(timezone.utc),
        expire_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(user)
    return user

# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_get_tiers_success(client, auth_headers):
    """查询会员等级权益对比成功。""
    resp = await client.get("/api/v1/membership/tiers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "tiers" in data
    assert len(data["tiers"]) >= 4  # free + member + pro + coach
    free_tier = next(t for t in data["tiers"] if t["tier"] == "free")
    assert free_tier["price_monthly_cents"] == 0
    member_tier = next(t for t in data["tiers"] if t["tier"] == "member")
    assert member_tier["price_monthly_cents"] == 1900  # ¥19 = 1900 分

@pytest.mark.asyncio
async def test_get_current_membership_member(client, db_session, member_user):
    """会员用户查询当前状态返回 active。""
    # 模拟登录 member_user
    headers = {"Authorization": f"Bearer test_token_{member_user.id}"}
    resp = await client.get("/api/v1/membership/current", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["status"] == "active"
    assert data["days_remaining"] > 0

@pytest.mark.asyncio
async def test_get_quota_free_user(client, auth_headers, db_session, free_user):
    """免费用户查询今日剩余免费分析次数。""
    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["daily_limit"] == 3
    assert data["remaining"] == 3

# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_get_current_no_subscription(client, auth_headers, db_session, free_user):
    """免费用户查询当前会员状态，tier 返回 free。""
    resp = await client.get("/api/v1/membership/current", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["status"] == "none"

# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_get_tiers_without_token(client):
    """未携带 JWT 返回 401。""
    resp = await client.get("/api/v1/membership/tiers")
    assert resp.status_code == 401

# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_quota_decrement_on_analysis(client, auth_headers, db_session, free_user):
    """免费用户分析一次后，剩余额度减1。""
    from app.services.membership_service import MembershipService
    # 模拟分析消耗一次额度
    consumed = await MembershipService.consume_analysis_quota(free_user.id)
    assert consumed is True
    # 查询额度
    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    data = resp.json()["data"]
    assert data["used_today"] == 1
    assert data["remaining"] == 2

@pytest.mark.asyncio
async def test_quota_exhausted(client, auth_headers, db_session, free_user):
    """免费用户额度用完后，消耗额度返回 False。""
    from app.services.membership_service import MembershipService
    # 消耗 3 次
    for _ in range(3):
        await MembershipService.consume_analysis_quota(free_user.id)
    # 第 4 次应失败
    consumed = await MembershipService.consume_analysis_quota(free_user.id)
    assert consumed is False

@pytest.mark.asyncio
async def test_member_unlimited_quota(client, db_session, member_user):
    """会员用户不消耗免费额度。""
    from app.services.membership_service import MembershipService
    consumed = await MembershipService.consume_analysis_quota(member_user.id)
    assert consumed is True  # 会员直接返回 True，不消耗额度。

@pytest.mark.asyncio
async def test_membership_expiry_detection(db_session, member_user):
    """到期检测：到期 3 天标记 expiring_soon。""
    from app.services.membership_service import MembershipService
    from app.models.membership import Subscription
    # 设置 expire_at 。2 天后
    sub = await db_session.execute(
        select(Subscription).where(Subscription.user_id == member_user.id)
    )
    subscription = sub.scalar_one()
    subscription.expire_at = datetime.now(timezone.utc) + timedelta(days=2)
    await db_session.commit()

    await MembershipService.check_expiry(db_session)
    await db_session.refresh(subscription)
    assert subscription.status == "expiring_soon"
```

---

## 3. Model（SQLAlchemy 2.0 async。）

```python
# app/models/membership.py
"""membership 模块 — 会员等级配置、订阅记录。""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class MembershipTier(Base):
    """会员等级配置（预置数据，运营可修改）。""
    __tablename__ = "membership_tier_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tier: Mapped[str] = mapped_column(String(20), unique=True, comment="等级标识：free/member/pro/coach")
    name: Mapped[str] = mapped_column(String(32), nullable=False, comment="等级名称")
    price_monthly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="月价（分）
    price_yearly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年价（分）
    price_quarterly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="季价（分）")
    benefits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, comment="权益列表")
    quota_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, comment="额度配置")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # R28-OBS-2: 保留 index=True（业务查询"激活的会员等级列表"常用过滤条件，DB §6.1 应补充声明此索引）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Subscription(Base):
    """用户订阅记录。""
    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, comment="会员等级")  # R19-P2-7: 统一 VARCHAR(20)（与 §2.17/§2.31/§5 对齐）
    status: Mapped[str] = mapped_column(
        String(20), default="active",
        comment="状态：active/expiring_soon/expired/grace_period/cancelled/closed",
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="取消时间（退款撤销时设置）")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    orders: Mapped[list["Order"]] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("idx_sub_user_status", "user_id", "status"),  # R18-P2-6: 索引命名对齐 §5/§6
        Index("idx_sub_status_expire", "status", "expire_at"),
    )
```
**预置等级数据**：

```python
# 预置会员等级配置
TIER_SEEDS = [
    {
        "tier": "free", "name": "免费",
        "price_monthly_cents": 0, "price_quarterly_cents": 0, "price_yearly_cents": 0,
        "benefits": ["每日 3 次分析, "记分。, "数据看板", "社区浏览"],
        "quota_config": {"daily_analysis_limit": 3},
        "sort_order": 0,
    },
    {
        "tier": "member", "name": "会员",
        "price_monthly_cents": 1900, "price_quarterly_cents": 4900, "price_yearly_cents": 16800,
        "benefits": ["无限分析", "训练方案", "训练单, "3D 教学", "历史对比"],
        "quota_config": {"daily_analysis_limit": -1},  # -1 表示无限
        "sort_order": 1,
    },
    {
        "tier": "pro", "name": "专业",
        "price_monthly_cents": 3900, "price_quarterly_cents": 9900, "price_yearly_cents": 35800,
        "benefits": ["无限分析", "高级分析", "对手建模", "月度报告", "训练方案"],
        "quota_config": {"daily_analysis_limit": -1},
        "sort_order": 2,
    },
    {
        "tier": "coach", "name": "教练",
        "price_monthly_cents": 9900, "price_quarterly_cents": 26900, "price_yearly_cents": 89900,
        "benefits": ["学员管理", "批量分析", "教练工具", "专业版全部权益],
        "quota_config": {"daily_analysis_limit": -1},
        "sort_order": 3,
    },
]
```

**实现后必须：
- [ ] 。`app/models/__init__.py` 中导入：`from app.models.membership import MembershipTier, Subscription`
- [ ] 运行 `alembic revision --autogenerate -m "add_membership_tables"`
- [ ] 运行 `alembic upgrade head`
- [ ] 预置会员等级数据（通过 Alembic data migration 。seed 脚本）

---

## 4. Schema（Pydantic。）

```python
# app/schemas/membership.py
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


# --- 响应 Schema ---
class TierBrief(BaseModel):
    """会员等级权益。""
    tier: str
    name: str
    price_monthly_cents: int
    price_quarterly_cents: int
    price_yearly_cents: int
    benefits: list[str]
    quota_config: dict

    model_config = {"from_attributes": True}


class TierListResponse(BaseModel):
    """会员等级列表响应。""
    tiers: list[TierBrief]

    model_config = {"from_attributes": True}


class CurrentMembershipResponse(BaseModel):
    """当前会员状态。""
    tier: str = "free"
    status: str = "none"
    start_at: Optional[str] = None
    expire_at: Optional[str] = None
    days_remaining: int = 0
    auto_renew: bool = False

    model_config = {"from_attributes": True}


class QuotaResponse(BaseModel):
    """今日剩余免费分析次数。""
    tier: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str

    model_config = {"from_attributes": True}


# --- 内部 Schema（供其他模块调用 ---
class MembershipCheckResult(BaseModel):
    """会员状态检查结果（供 video_analysis 等模块调用）。""
    tier: str = "free"
    is_member: bool = False
    has_quota: bool = True
    daily_limit: int = 3
    used_today: int = 0
    remaining: int = 3
```

---

## 5. Service 实现（@staticmethod。）

```python
# app/services/membership_service.py
"""membership 业务逻辑 — 等级查询、状态管理、免费额度控制、到期检测。""
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.membership import MembershipTier, Subscription
from app.schemas.membership import (
    TierListResponse, TierBrief,
    CurrentMembershipResponse, QuotaResponse, MembershipCheckResult,
)
from app.services.notification_service import NotificationService


class MembershipService:
    """membership 业务逻辑层。""

    # Redis Key 统一使用 f-string 内联构造（如 f"quota:analysis:{user_id}:{date}"）
    # 不再使用类常量模板 + .format()，与全项目风格保持一致
    TIER_CACHE_KEY = "membership:tiers"
    TIER_CACHE_TTL = 3600  # 1 小时
    FREE_DAILY_LIMIT = 3
    GRACE_PERIOD_DAYS = 7
    EXPIRING_SOON_DAYS = 3

    # ===================== 公开方法（API 调用）。=====================

    @staticmethod
    async def get_tiers(db: AsyncSession) -> TierListResponse:
        """查询会员等级权益对比（缓。h）。""
        # 优先读 Redis 缓存
        redis = await get_redis()
        cached = await redis.get(MembershipService.TIER_CACHE_KEY)
        if cached:
            import json
            data = json.loads(cached)
            return TierListResponse(**data)

        # 查数据库
        result = await db.execute(
            select(MembershipTier)
            .where(MembershipTier.is_active == True)
            .order_by(MembershipTier.sort_order)
        )
        tiers = result.scalars().all()
        tier_list = [
            TierBrief(
                tier=t.tier, name=t.name,
                price_monthly_cents=t.price_monthly_cents, price_quarterly_cents=t.price_quarterly_cents, price_yearly_cents=t.price_yearly_cents,
                benefits=t.benefits if isinstance(t.benefits, list) else list(t.benefits),
                quota_config=t.quota_config if isinstance(t.quota_config, dict) else dict(t.quota_config),
            )
            for t in tiers
        ]
        response = TierListResponse(tiers=tier_list)

        # 回填缓存
        import json
        await redis.setex(
            MembershipService.TIER_CACHE_KEY,
            MembershipService.TIER_CACHE_TTL,
            response.model_dump_json(),
        )

        return response

    @staticmethod
    async def get_current_membership(db: AsyncSession, user_id: int) -> CurrentMembershipResponse:
        """查询当前会员状态。""
        subscription = await MembershipService._get_active_subscription(db, user_id)

        if subscription is None:
            return CurrentMembershipResponse(
                tier="free",
                status="none",
                days_remaining=0,
            )

        # 实时校验兜底（即。Celery 未运行也能检测到期）
        now = datetime.now(timezone.utc)
        if subscription.status == "active" and subscription.expire_at < now:
            # 已到期但状态尚未更新
            await MembershipService._handle_expiry(db, subscription)
            await db.commit()

        if subscription.status == "active" and \
           subscription.expire_at < now + timedelta(days=MembershipService.EXPIRING_SOON_DAYS):
            # 即将到期
            subscription.status = "expiring_soon"
            await db.commit()

        days_remaining = max(0, (subscription.expire_at - now).days)

        return CurrentMembershipResponse(
            tier=subscription.tier,
            status=subscription.status,
            start_at=subscription.start_at.isoformat() if subscription.start_at else None,
            expire_at=subscription.expire_at.isoformat(),
            days_remaining=days_remaining,
            auto_renew=subscription.auto_renew,
        )

    @staticmethod
    async def get_quota(db: AsyncSession, user_id: int) -> QuotaResponse:
        """查询今日剩余免费分析次数。""
        membership = await MembershipService.get_current_membership(db, user_id)

        # 会员用户无限。
        if membership.tier != "free":
            return QuotaResponse(
                tier=membership.tier,
                daily_limit=-1,
                used_today=0,
                remaining=-1,  # -1 表示无限
                reset_at="",
            )

        # 免费用户：读 Redis 计数器
        today = datetime.now(timezone(timedelta(hours=8))).date()
        used_today = await MembershipService._get_used_count(user_id, today)

        remaining = max(0, MembershipService.FREE_DAILY_LIMIT - used_today)
        reset_at = MembershipService._get_reset_time(today)

        return QuotaResponse(
            tier="free",
            daily_limit=MembershipService.FREE_DAILY_LIMIT,
            used_today=used_today,
            remaining=remaining,
            reset_at=reset_at.isoformat(),
        )

    # ===================== 供其他模块调用 =====================

    @staticmethod
    async def check_membership(db: AsyncSession, user_id: int) -> MembershipCheckResult:
        """
        检查用户会员状态（供 video_analysis 等模块调用）。
        返回用户等级、是否会员、是否有剩余额度。
        """
        subscription = await MembershipService._get_active_subscription(db, user_id)

        if subscription is None:
            # 免费用户
            today = datetime.now(timezone(timedelta(hours=8))).date()
            used_today = await MembershipService._get_used_count(user_id, today)
            remaining = max(0, MembershipService.FREE_DAILY_LIMIT - used_today)
            return MembershipCheckResult(
                tier="free",
                is_member=False,
                has_quota=remaining > 0,
                daily_limit=MembershipService.FREE_DAILY_LIMIT,
                used_today=used_today,
                remaining=remaining,
            )

        # 会员用户
        return MembershipCheckResult(
            tier=subscription.tier,
            is_member=True,
            has_quota=True,  # 无限
            daily_limit=-1,
            used_today=0,
            remaining=-1,
        )

    @staticmethod
    async def consume_analysis_quota(user_id: int) -> bool:
        """
        消耗一次分析额度（Redis 原子操作）。
        - 会员用户：直接返回 True，不消耗额度
        - 免费用户：INCR 计数器，超过限制则返回 False
        
        由 video_analysis 模块 POST /video-analysis/tasks 时调用。
        """
        # TODO: Phase 2 统一额度管理——video_analysis._check_free_quota 应调用此方法
        # 先检查会员状态（需要数据库会话）
        from app.core.database import get_async_session
        async with get_async_session() as db:
            membership = await MembershipService.check_membership(db, user_id)

        if membership.is_member:
            return True  # 会员无限

        if not membership.has_quota:
            return False  # 额度已用完

        # 原子操作：INCR 后检查是否超额
        today = datetime.now(timezone(timedelta(hours=8))).date()
        redis = await get_redis()
        key = f"quota:analysis:{user_id}:{today.isoformat()}"

        new_count = await redis.incr(key)

        # 首次设置 TTL（到当日 23:59:59 + 1h）
        if new_count == 1:
            ttl = MembershipService._seconds_until_reset(today)
            await redis.expire(key, ttl)

        if new_count > MembershipService.FREE_DAILY_LIMIT:
            # 超额，回退
            await redis.decr(key)
            return False

        return True

    # ===================== 到期检测（Celery Beat 调用）。=====================

    @staticmethod
    async def check_expiry(db: AsyncSession) -> None:
        """
        到期检测：Celery Beat 每日 00:30 执行。
        1. 到期 3 天 → 标记 + 发送续费提醒。
        2. 到期 。expired + 触发权益降级
        3. 到期7天后 。closed
        """
        now = datetime.now(timezone.utc)

        # 1. 标记即将到期 3 天内
        expiring_soon_threshold = now + timedelta(days=MembershipService.EXPIRING_SOON_DAYS)
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status == "active",
                Subscription.expire_at < expiring_soon_threshold,
                Subscription.expire_at >= now,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "expiring_soon"
            # 发送到期提醒
            await MembershipService._send_expiry_notification(sub)

        # 2. 标记已到期
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status.in_(["active", "expiring_soon"]),
                Subscription.expire_at < now,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "expired"
            # 触发权益降级
            await MembershipService._handle_downgrade(db, sub)

        # 3. 标记已关闭（到期7天后）
        closed_threshold = now - timedelta(days=MembershipService.GRACE_PERIOD_DAYS)
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status == "expired",
                Subscription.expire_at < closed_threshold,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "closed"

        await db.commit()

    # ===================== 内部方法 =====================

    @staticmethod
    async def _get_active_subscription(
        db: AsyncSession, user_id: int
    ) -> Optional[Subscription]:
        """获取用户当前有效订阅。""
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "expiring_soon", "expired", "grace_period"]),
            )).order_by(Subscription.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_used_count(user_id: int, today: date) -> int:
        """从 Redis 获取今日已用分析次数。""
        redis = await get_redis()
        key = f"quota:analysis:{user_id}:{today.isoformat()}"
        count = await redis.get(key)
        return int(count) if count else 0

    @staticmethod
    def _get_reset_time(today: date) -> datetime:
        """获取额度重置时间（次。00:00）。""
        tomorrow = today + timedelta(days=1)
        # 使用 Asia/Shanghai 时区
        from datetime import timezone, timedelta as td
        shanghai_tz = timezone(td(hours=8))
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=shanghai_tz)

    @staticmethod
    def _seconds_until_reset(today: date) -> int:
        """计算到次。00:00 的秒数（Redis TTL）。""
        reset_at = MembershipService._get_reset_time(today)
        now = datetime.now(reset_at.tzinfo)
        return int((reset_at - now).total_seconds()) + 3600  # 额外1小时缓冲

    @staticmethod
    async def _handle_expiry(db: AsyncSession, subscription: Subscription) -> None:
        """处理到期逻辑（实时兜底）。""
        subscription.status = "expired"
        await MembershipService._handle_downgrade(db, subscription)

    @staticmethod
    async def apply_downgrade_policy(db: AsyncSession, subscription: Subscription) -> None:
        """
        实现 BR-3 权益降级策略（模块详细设计 BR-3）。
        会员到期后各功能的降级处理：
        - 历史报告：只读（禁止新增/编辑/删除）
        - 标注视频：保留 30 天后清理（设置 30 天 TTL 标记）
        - 3D 教学：隐藏入口（前端根据 tier 判断）
        - 进度分析：隐藏入口（前端根据 tier 判断）
        - 数据看板：降级为简化版（前端根据 tier 判断）
        """
        redis = await get_redis()
        import json

        user_id = subscription.user_id

        # 1. 历史报告 。只读
        # 使用 set 而非 setex(key, 0, ...)：setex 。TTL=0 。Redis 中会报错或立即删除 key
        await redis.set(
            f"downgrade:report:readonly:{user_id}",
            json.dumps({"readonly": True}),
        )

        # 2. 标注视频 。保留 30 天后清理
        cleanup_at = datetime.now(timezone.utc) + timedelta(days=30)
        await redis.setex(
            f"downgrade:video:cleanup:{user_id}",
            int(30 * 24 * 3600),  # 30 天 TTL
            json.dumps({
                "retain_days": 30,
                "cleanup_at": cleanup_at.isoformat(),
            }),
        )

        # 3. & 4. 3D 教学 / 进度分析 。隐藏入口（前端根。tier=free 判断）
        #    无需额外 Redis 标记，前端通过 get_current_membership 返回的 tier 判断

        # 5. 数据看板 。降级为简化版（前端根。tier=free 判断）
        #    无需额外 Redis 标记，前端通过 get_current_membership 返回的 tier 判断

        # 推送降级事件，通知前端立即生效
        await NotificationService.push_ws_message(user_id, "membership_downgrade", {
            "user_id": user_id,
            "old_tier": subscription.tier,
            "new_tier": "free",
            "downgrade_policy": {
                "report_readonly": True,
                "video_cleanup_days": 30,
                "hide_3d_teaching": True,
                "hide_progress_analysis": True,
                "dashboard_simplified": True,
            },
        })

    @staticmethod
    async def _handle_downgrade(db: AsyncSession, subscription: Subscription) -> None:
        """权益降级处理（调用 apply_downgrade_policy 实现 BR-3）。""
        await MembershipService.apply_downgrade_policy(db, subscription)

    @staticmethod
    async def revoke_subscription(db: AsyncSession, subscription_id: int) -> None:
        """退款后撤销会员权益（P0-REVOKE 修复：payment 模块调用）。
        根据 subscription_id 查询 Subscription 对象。        设置 status="closed"，然后调。apply_downgrade_policy 执行降级。        """
        subscription = await db.scalar(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        if not subscription:
            return  # 订阅不存在，静默返回
        subscription.status = "closed"
        subscription.cancelled_at = datetime.now(timezone.utc)
        await db.flush()
        await MembershipService.apply_downgrade_policy(db, subscription)
        await db.commit()

    @staticmethod
    async def _send_expiry_notification(subscription: Subscription) -> None:
        """发送到期续费提醒（WS 推。+ 微信订阅消息）。""
        redis = await get_redis()
        import json
        days_remaining = max(0, (subscription.expire_at - datetime.now(timezone.utc)).days)
        await NotificationService.push_ws_message(subscription.user_id, "notification", {
            "type": "membership_expiring",
            "title": "会员即将到期",
            "content": f"您的{subscription.tier}会员将在{days_remaining}天后到期，请及时续费",
            "user_id": subscription.user_id,
        })
        # X-14 修复：同时发送微信订阅消。        await MembershipService._send_wechat_subscribe(subscription)

    @staticmethod
    async def _send_wechat_subscribe(subscription: Subscription) -> None:
        """发送微信订阅消息（会员到期提醒）。
        X-14 修复：通过微信订阅消息接口发送到期提醒，
        补充 WebSocket 推送之外的触达渠道。        """
        import logging
        logger = logging.getLogger(__name__)
        try:
            # 调用微信订阅消息 API（需。app/core/wechat.py 中实现 send_subscribe_message。            from app.core.wechat import send_subscribe_messaged_subscribe_message
            await send_subscribe_message(
                user_id=subscription.user_id,
                template_id="membership_expiry_reminder",
                page=f"/pages/membership/index?subscription_id={subscription.id}",
                data={
                    "thing1": {"value": f"您的{subscription.tier}会员即将到期"},
                    "date2": {"value": subscription.expire_at.strftime("%Y-%m-%d")},
                    "thing3": {"value": "点击续费继续享受会员权益"},
                },
            )
        except ImportError:
            logger.warning("wechat subscribe message module not available")
        except Exception as e:
            logger.error("wechat_subscribe_failed", user_id=subscription.user_id, error=str(e))
```

---

## 6. API 路由实现（FastAPI。）

```python
# app/api/v1/membership/router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.membership import (
    TierListResponse, CurrentMembershipResponse, QuotaResponse,
)
from app.services.membership_service import MembershipService

router = APIRouter(prefix="/membership", tags=["会员-等级权益"])


@limiter.limit("100/minute")
@router.get("/tiers", summary="会员等级与权益对比")
async def get_tiers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询会员等级权益对比表（缓存1h）。""
    data = await MembershipService.get_tiers(db)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/current", summary="当前会员状态")
async def get_current_membership(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前会员状态（含到期时间、剩余天数）。""
    data = await MembershipService.get_current_membership(db, user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/quota", summary="今日剩余免费分析次数")
async def get_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询今日剩余免费分析次数（Redis 计数器）。""
    data = await MembershipService.get_quota(db, user.id)
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.membership.router import router as membership_router
api_router.include_router(membership_router)
```

---

## 7. Celery Beat 到期检测任务

```python
# app/tasks/membership_tasks.py
"""membership Celery 定时任务 。会员到期检测。""
from celery import shared_task
from app.core.database import get_async_session
from app.services.membership_service import MembershipService
import logging

logger = logging.getLogger(__name__)


@shared_task(name="membership.check_expiry")
def check_membership_expiry():
    """
    会员到期检测任务。
    Celery Beat 配置：每天 00:30 执行。
    crontab: 30 0 * * *
    """
    import asyncio
    async def _run():
        async with get_async_session() as db:
            await MembershipService.check_expiry(db)
            logger.info("Membership expiry check completed")
    asyncio.run(_run())


# Celery Beat 配置（在 celery_app.py 。settings 中）:
# beat_schedule = {
#     "membership-check-expiry": {
#         "task": "membership.check_expiry",
#         "schedule": crontab(hour=0, minute=30),  # 每日 00:30
#     },
# }
```

---

## 8. 冒烟测试脚本

```python
# tests/smoke/membership_smoke_test.py
"""
membership 模块冒烟测试
用法: python -m tests.smoke.membership_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("1. Testing login...")
        login_resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "membership冒烟测试",
        })
        if login_resp.status_code != 200:
            print(f"   ✗ Login failed: {login_resp.status_code}")
            return
        token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("   ✓ Login success")

        # 2. 查询会员等级
        print("2. Testing GET /membership/tiers...")
        resp = await client.get("/membership/tiers", headers=headers)
        assert resp.status_code == 200, f"Tiers failed: {resp.text}"
        tiers = resp.json()["data"]["tiers"]
        print(f"   ✓ Tiers: {len(tiers)} levels")
        for tier in tiers:
            print(f"     - {tier['name']}: ¥{tier['price_monthly_cents']/100:.0f}/。)

        # 3. 查询当前会员状态
        print("3. Testing GET /membership/current...")
        resp = await client.get("/membership/current", headers=headers)
        assert resp.status_code == 200, f"Current failed: {resp.text}"
        current = resp.json()["data"]
        print(f"   ✓ Current: tier={current['tier']}, status={current['status']}")

        # 4. 查询今日额度
        print("4. Testing GET /membership/quota...")
        resp = await client.get("/membership/quota", headers=headers)
        assert resp.status_code == 200, f"Quota failed: {resp.text}"
        quota = resp.json()["data"]
        print(f"   ✓ Quota: tier={quota['tier']}, remaining={quota['remaining']}/{quota['daily_limit']}")

    print("\nmembership_smoke_test: ALL PASSED ✓)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_membership.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.membership_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导出
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] Alembic 迁移已生成并执行
- [ ] 会员等级种子数据已预置（free/member/pro/coach 4 个等级）
- [ ] 定价正确：免费 ¥0 / 会员 ¥19月¥49季¥168年 / 专业 ¥39月¥99季¥358年 / 教练 ¥99月¥269季¥899年
- [ ] Redis 额度计数器键格式正确（`quota:analysis:{user_id}:{date}`）
- [ ] 免费额度每日 00:00 (Asia/Shanghai) 重置，不累积，过期清理
- [ ] 到期检测 Celery Beat 任务配置正确（每天 00:30）
- [ ] 实时校验兜底正确（每次请求会员功能时检查 expire_at）
- [ ] 订阅生命周期状态正确（active → expiring_soon → expired → grace_period → closed）
- [ ] WS 推送 `membership_downgrade` 和 `notification`（到期提醒）事件格式正确
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`TierListResponse`、`CurrentMembershipResponse`、`QuotaResponse`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 免费额度 **必须** 使用 Redis 计数器实现，**禁止** 使用数据库表计数
- 额度计数 **必须** 使用原子 INCR 操作 + 超额回退（DECR）
- Redis 额度键 **必须** 设置 TTL（到次日 00:00 + 1h 缓冲）
- 到期检测 **必须** 使用 Celery Beat 定时任务 + 实时校验兜底双层保障
- 权益降级策略 **必须** 。BR-3 表格执行（历史报告只。标注视频30。3D教学隐藏等）
- `consume_analysis_quota` 方法 **必须** 先检查会员状态再决定是否消耗额度
- **覆盖度修复：已根据覆盖度分析报告修。A-9（`datetime.utcnow()` naive 。timezone-aware，`default`/`onupdate` 改为 lambda 表达式，import 补充 `timezone`）
- **覆盖度修。X-6**：MembershipTier 表名 `membership_tier` → `membership_tier_config`（对齐 DB 设计 §2.31）；字段 `price_monthly` → `price_monthly_cents`、`price_yearly` → `price_yearly_cents`（单位分，nullable）、`quota` → `quota_config`（对齐 DB 设计字段名）；`is_active`/`created_at`/`updated_at` 标注为切片新增（DB 设计 §2.31 已对齐DB设计）；同步更新 TIER_SEEDS 种子数据、TierBrief Schema、get_tiers Service、测试断言、冒烟测试中的字段引用
- **覆盖度修。X-11**：Subscription 表删除多余 `period` 字段。`order_id` 字段（DB 设计 §2.17 已对齐DB设计）；cancelled 状态在第十三轮重新加入合法枚举，用于用户注销场景；新增 `payment_method` 字段（DB 设计 §2.17 定义）
- **覆盖度修。X-12**：新增 `apply_downgrade_policy` 方法实现 BR-3 权益降级策略（历史报告只读 / 标注视频保留30天后清理/3D教学隐藏入口/进度分析隐藏入口/数据看板降级为简化版）；`_handle_downgrade` 改为调用 `apply_downgrade_policy`，签名增加 `db` 参数；同步更新 `check_expiry` 在 `_handle_expiry` 中的调用
- 所有 API 端点 **必须** 添加 `@limiter.limit("100/minute")` 限流装饰器，**禁止** 裸奔无限流
- `from app.core.limiter import limiter` **必须** 在路由文件 import 区声明，**禁止** 遗漏导入
