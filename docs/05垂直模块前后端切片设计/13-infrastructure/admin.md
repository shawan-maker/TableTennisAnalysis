min 基础设施模块 — 后端垂直切片设计

> **模块名称**：`admin`
> **所属目录**：`app/api/v1/admin/` + `app/services/admin_service.py`
> **定位**：管理员认证、用户管理、内容审核、系统配置管理、知识库管理、审计日志
> **依据**：模块详细设计 v1.2 §3.5、数据库详细设计 v1.5 §2.31

---

## 1. 模块概述

> **设计对齐说明（X-16 已解决）**：架构文档 §4.1 已更新，admin 模块 Phase 1 暴露管理 API 为正式设计决策。
> 管理后台是 Phase 1 运营必需的基础设施（用户管理、内容审核、系统配置），通过 RBAC 角色守卫（get_current_admin / require_super_admin）控制访问权限，无需额外 Phase 守卫机制。
> 模块详细设计 §3.5 MA-1 偏差说明已同步更新。

| 属性 | 值 |
|------|-----|
| 模块名称 | `admin` |
| 所属目录 | `app/api/v1/admin/` |
| 一句话定位 | 管理员独立认证、用户管理、内容审核、系统配置管理、知识库 CRUD、审计日志 |
| 关联数据表 | admin_user, audit_log, system_config, user (封禁/解禁), knowledge_base (CRUD) |
| 依赖模块 | auth（独立 AdminUser 认证）, knowledge_base, ai_inference |
| 前端 | Phase 1 无独立前端，通过内部 API 供管理工具调用 |

### 核心功能

- **管理员独立认证**：AdminUser 表（用户名+密码，bcrypt），session Redis 30min，**不使用 JWT**
- **用户管理**：封禁/解禁、角色调整、列表查询
- **内容审核队列**：Phase 3 社区上线后激活（Phase 1 预留接口）
- **数据飞轮反馈审核队列**：Phase 2+ 激活。当用户反馈 `is_correct=false` 时，`feedback_record.status` 设为 `manual_review`，管理员在后台审核修正标注后将 status 改为 `archived` 并触发 `FileService.archive_for_training` 归档到 OSS `annotations/` 目录。Phase 1 仅预留 `status` 字段和查询接口设计，不实现审核 UI。
- **系统配置管理**：键值对 CRUD + Redis 缓存热更新
- **审计日志查询**：按管理员/操作类型/时间筛选
- **知识库 CRUD**：分类/条目/规则/模板的增删改查
- **模型版本管理**：Phase 2+ 模型版本切换
- **全操作审计**：所有管理操作写入 audit_log（changes JSONB `{field:{old,new}}`）

---

## 2. 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/admin.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/admin.py` | #1 | ☐ |
| 4 | 实现认证依赖 | `app/core/admin_deps.py` | #1 | ☐ |
| 5 | 实现 Service | `app/services/admin_service.py` | #2,#3,#4 | ☐ |
| 6 | 实现 API 路由 | `app/api/v1/admin/router.py` | #5 | ☐ |
| 7 | 注册 Router | `app/api/v1/__init__.py` | #6 | ☐ |
| 8 | 编写测试 | `tests/unit/test_admin.py` | #5 | ☐ |
| 9 | 编写冒烟测试 | `tests/smoke/admin_smoke_test.py` | #7 | ☐ |

---

## 3. Model 实现

```python
# app/models/admin.py
"""管理后台数据模型。"""

from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Boolean, Integer, ForeignKey, Text, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class AdminUser(Base):
    """管理员用户。"""
    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    """bcrypt 密码哈希"""
    role: Mapped[str] = mapped_column(String(20))
    """角色: super_admin / content_admin / model_admin"""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # R19-P1-1: 补充（§2.31/§5 已定义，R18-P3-5 闭环缺口）


class AuditLog(Base):
    """操作审计日志。"""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_user.id", ondelete="RESTRICT"), nullable=False)
    """管理员 ID（所有审计日志必须关联管理员）"""
    action: Mapped[str] = mapped_column(String(32))
    """操作: create / update / delete / publish / reject / payment_order_created / payment_callback_processed / payment_refunded / subscription_created_or_renewed"""
    target_type: Mapped[str] = mapped_column(String(32))
    """目标类型: user / report / video / model / config / knowledge / order / subscription"""
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """变更内容: {field: {old, new}}（管理员操作使用）"""
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    """用户 ID（非管理员操作时填写，如支付模块订单创建/回调/退款）"""
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    """操作详情 JSON 字符串（支付等模块使用，如 {amount, product_type, tier}）"""
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    """操作者 IP 地址（支持 IPv4/IPv6）"""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_audit_admin_created", "admin_id", "created_at"),
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_target", "target_type", "target_id"),
    )


class SystemConfig(Base):
    """系统配置。"""
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(64), unique=True)
    config_value: Mapped[dict] = mapped_column(JSONB)
    """配置值（JSONB 格式，支持任意类型）"""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入 3 个 Model
- [ ] 运行 `alembic revision --autogenerate -m "add admin tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/admin.py
"""管理后台 Schema 定义。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- 请求 Schema ---
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


# R4-Admin-19: 字段名 key/value → config_key/config_value
# R13-P3 文档同步: config_value 类型 Any → str | dict（与实际实现一致）
class ConfigCreateRequest(BaseModel):
    config_key: str = Field(..., max_length=64)
    config_value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    config_value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


class UserBanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# R4-Admin-3: content 字段；R13-P3 文档同步: content 可选（default_factory=dict），
# name/code 仅 max_length 约束（无 min_length）
class CategoryCreateRequest(BaseModel):
    name: str = Field(..., max_length=64)
    code: str = Field(..., max_length=32)
    content: dict = Field(default_factory=dict, description="分类内容")


# R4-Admin-11: 仅允许 name 和 content 字段（不允许更新 code）
class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    content: Optional[dict] = Field(default=None, description="分类内容")


# R4-Admin-12: training_methods 类型 list；adjustment_action 长度约束
class RuleCreateRequest(BaseModel):
    rule_id: str = Field(..., max_length=64)
    rule_name: str = Field(..., max_length=128)
    rule_type: str = Field(..., max_length=32)
    condition: dict
    diagnosis: dict
    training_methods: Optional[list] = None
    training_plan_template: Optional[str] = None
    adjustment_action: Optional[str] = Field(
        default=None, max_length=32,
        description="调整动作 maintain/adjust/escalate/new_goal",
    )


# --- 响应 Schema ---
# R4-Admin-17: AdminBrief 先定义，AdminLoginResponse 直接类型引用
class AdminBrief(BaseModel):
    id: int
    username: str
    role: str
    model_config = {"from_attributes": True}


class AdminLoginResponse(BaseModel):
    session_token: str
    admin: AdminBrief
    expires_in: int = 1800


class UserManageBrief(BaseModel):
    id: int
    nickname: str
    phone: Optional[str] = None
    openid: Optional[str] = None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


# R4-Admin-15: updated_at；R13-P3 文档同步: 补 created_at、config_value 可空
class ConfigBrief(BaseModel):
    id: int
    config_key: str
    config_value: str | dict | None = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# R4-Admin-9+10: admin_username（list_audit_logs LEFT JOIN 填充）
# R6-Admin-5+6: admin_id/target_type 可空（用户侧支付等操作无 admin_id）
class AuditLogBrief(BaseModel):
    id: int
    admin_id: Optional[int] = None
    admin_username: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    changes: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


AdminLoginResponse.model_rebuild()

# R13-P3 文档同步: 原设计的 UserListQuery / AuditLogQuery / Paginated[...] 包装类型未采用。
# 实际 Router 用 Query() 散参、Service 散参签名，分页统一返回 dict
# {total, page, page_size, items}（items 为 Pydantic Brief 列表）。
```

---

## 5. Service 实现

### 5.1 管理员认证依赖

```python
# app/core/deps.py（R13-P3 文档同步: 实际实现位于 core/deps.py，未创建独立 admin_deps.py）
"""管理员认证依赖——独立于普通用户 JWT 体系。"""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException, ERR_FORBIDDEN, ERR_UNAUTHORIZED


# Session TTL（30 分钟，滑动续期见 refresh_session）
ADMIN_SESSION_TTL = 1800


async def get_admin_session(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Admin 独立认证——基于 Redis session，不使用 JWT。

    流程：
    1. 解析 Authorization header（R5-Admin-4: 支持 "Admin xxx" / "Bearer xxx" 两种前缀）
    2. Redis 查询 admin:session:{token} → session JSON {admin_id, username, role}
    3. R12-Admin-1: 每请求校验 admin_user.is_active —— 禁用/删除的管理员
       session 立即失效（删除 Redis key 并返回 403）
    4. 滑动续期：refresh_session 将 TTL 刷新至 30 分钟（R12-Admin-13）
    """
    from app.services.admin_service import AdminService, ADMIN_SESSION_PREFIX

    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        raise AppException("管理员请先登录", 401, code=ERR_UNAUTHORIZED)

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0] not in ("Admin", "Bearer"):
        raise AppException("管理员请先登录", 401, code=ERR_UNAUTHORIZED)

    token = parts[1]
    session = await AdminService.get_session(token)
    if not session:
        raise AppException("管理员会话已过期，请重新登录", 401, code=ERR_UNAUTHORIZED)

    # R12-Admin-1: 每请求校验管理员状态 —— 禁用/删除的管理员 session 立即失效
    admin_id = session.get("admin_id")
    if admin_id is not None:
        from app.models.admin import AdminUser

        result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin is None or not admin.is_active:
            from app.core.redis import get_redis

            redis_client = await get_redis()
            await redis_client.delete(f"{ADMIN_SESSION_PREFIX}{token}")
            raise AppException("管理员账号已被禁用", 403, code=ERR_FORBIDDEN)

    # 刷新 session TTL（滑动续期）
    await AdminService.refresh_session(token)
    return session


async def require_super_admin(session: dict = Depends(get_admin_session)) -> dict:
    """超级管理员权限守卫（基于 session.role）。"""
    if session.get("role") != "super_admin":
        raise AppException("需要超级管理员权限", 403, code=ERR_FORBIDDEN)
    return session


# 另有 require_content_admin / require_model_admin（super_admin 也通过），见 app/core/deps.py。
# R13-P3 文档同步: 路由端依赖为 session: dict = Depends(get_admin_session)，
# 业务调用取 session["admin_id"]；session 值为 JSON {admin_id, username, role}，
# 非原设计的 str(admin.id)；认证依赖返回 session dict 而非 AdminUser ORM 对象。
```

### 5.2 Admin Service

```python
# app/services/admin_service.py
"""管理后台业务逻辑层。

R13-P3 文档同步（以实际实现为准）：
- session 为 JSON {admin_id, username, role}（非 str(admin.id)）
- 登录密码验证用 passlib bcrypt（pwd_context.verify），并更新 last_login_at
- Service 方法为散参签名（非 Query 对象），分页返回 dict {total,page,page_size,items}
- 审计写入使用独立 session（R5-Admin-6），业务 commit 后调用（R12-Admin-6）
- 下方样例省略（...）的方法体与 app/services/admin_service.py 完全一致
"""

import json
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.core.exceptions import AppException, ERR_NOT_FOUND, ERR_CONFLICT, ERR_FORBIDDEN
from app.core.security import pwd_context
from app.models.admin import AdminUser, SystemConfig, AuditLog
from app.models.user import User
from app.models.knowledge_base import KnowledgeCategory, RuleDefinition
from app.schemas.admin import (
    AdminBrief, AdminLoginResponse, UserManageBrief, ConfigBrief, AuditLogBrief,
)

logger = logging.getLogger(__name__)

ADMIN_SESSION_TTL = 1800  # 30 分钟
ADMIN_SESSION_PREFIX = "admin:session:"

# R4-Admin-7+8: 配置缓存常量
CONFIG_CACHE_PREFIX = "config:"
CONFIG_CACHE_TTL = 3600  # 1 小时


class AdminService:
    """管理后台业务逻辑层。"""

    # ==================== Admin 认证 ====================

    @staticmethod
    async def login(username: str, password: str) -> AdminLoginResponse:
        """管理员登录——passlib bcrypt 验证，签发 JSON session（30min TTL）。

        R13-P3 文档同步: 密码验证用 pwd_context.verify（passlib bcrypt，
        非 bcrypt.checkpw 直调）；session 值为 JSON {admin_id, username, role}；
        登录成功更新 last_login_at；禁用账号返回 403。
        """
        async with async_session_factory() as db:
            result = await db.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            admin = result.scalar_one_or_none()

            if not admin or not pwd_context.verify(password, admin.password_hash):
                raise AppException("用户名或密码错误", 401)

            if not admin.is_active:
                raise AppException("管理员账号已禁用", 403)

            # 更新最后登录时间
            admin.last_login_at = datetime.now(timezone.utc)
            await db.commit()

        # 创建 Redis session（JSON 结构）
        token = secrets.token_urlsafe(32)
        redis = await get_redis()
        session_data = json.dumps({
            "admin_id": admin.id,
            "username": admin.username,
            "role": admin.role,
        })
        await redis.set(f"{ADMIN_SESSION_PREFIX}{token}", session_data, ex=ADMIN_SESSION_TTL)

        return AdminLoginResponse(
            session_token=token,
            admin=AdminBrief(id=admin.id, username=admin.username, role=admin.role),
            expires_in=ADMIN_SESSION_TTL,
        )

    @staticmethod
    async def logout(token: str) -> None:
        """管理员登出——删除 Redis session。"""
        redis = await get_redis()
        await redis.delete(f"{ADMIN_SESSION_PREFIX}{token}")

    @staticmethod
    async def get_session(token: str) -> dict | None:
        """获取 admin session（JSON 反序列化为 dict）。"""
        redis = await get_redis()
        data = await redis.get(f"{ADMIN_SESSION_PREFIX}{token}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def refresh_session(token: str) -> None:
        """滑动续期——刷新 session TTL 至 30 分钟（R12-Admin-13）。"""
        redis = await get_redis()
        await redis.expire(f"{ADMIN_SESSION_PREFIX}{token}", ADMIN_SESSION_TTL)

    # ==================== 审计日志 ====================

    @staticmethod
    async def _write_audit_log(
        db: AsyncSession,  # 保留参数兼容现有调用，实际使用独立 session
        admin_id: int | None,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        changes: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """写审计日志（内部方法）——独立 session 提交，异常吞噬不阻塞业务。

        R5-Admin-6: 独立 async_session_factory()，审计独立提交，不随业务事务回滚丢失。
        R4-Admin-4: 失败仅记 error 日志，不 re-raise。
        """
        try:
            async with async_session_factory() as audit_db:
                log = AuditLog(
                    admin_id=admin_id,
                    user_id=None,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    changes=changes or {},
                    ip_address=ip_address,
                )
                audit_db.add(log)
                await audit_db.commit()
        except Exception as e:
            logger.error(
                "Failed to write audit log: admin_id=%s action=%s error=%s",
                admin_id, action, e, exc_info=True,
            )

    # ==================== 用户管理 ====================

    @staticmethod
    async def list_users(
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """用户列表查询（散参签名；返回 dict {total,page,page_size,items}，
        items 为 UserManageBrief 列表，page_size 上限 100）。"""
        ...

    # R13-P3 文档同步: 实际签名 ban_user(user_id, reason, admin_id)（user_id 在前）
    @staticmethod
    async def ban_user(user_id: int, reason: str, admin_id: int) -> dict:
        """封禁用户——重复封禁 409；审计在业务 commit 后写入（R12-Admin-6），
        changes 记 {status, ban_reason} 字段级 old/new（R4-Admin-6）。"""
        ...

    @staticmethod
    async def unban_user(user_id: int, admin_id: int) -> dict:
        """解禁用户——未被封禁 409；返回 {"user_id", "status"}。"""
        ...

    # ==================== 系统配置 ====================

    @staticmethod
    async def list_configs() -> list[ConfigBrief]:
        ...

    # R4-Admin-7+8: Redis 缓存优先；update/delete 失效缓存
    @staticmethod
    async def get_config(key: str) -> ConfigBrief:
        """获取单个配置——Redis 缓存优先（TTL 3600s），未命中回查 DB 并回填
        完整 ConfigBrief（model_dump_json）。缓存读写失败降级（try/except + warning）。"""
        ...

    @staticmethod
    async def create_config(key: str, value: str, description: str | None, admin_id: int) -> ConfigBrief:
        """创建配置——重复 key 409；审计移到 commit 后并传 target_id=config.id
        （R9-Admin-P2-1）。"""
        ...

    @staticmethod
    async def update_config(key: str, value: str, description: str | None, admin_id: int) -> ConfigBrief:
        """更新配置——commit 后审计 changes {config_value: {old,new}}（R12-Admin-5），
        DEL config:{key} 失效缓存（容错降级）。"""
        ...

    @staticmethod
    async def delete_config(key: str, admin_id: int) -> None:
        """删除配置——commit 后审计 + DEL 缓存。"""
        ...

    # ==================== 审计日志查询 ====================

    # R4-Admin-9+10: admin_id/start_date/end_date 筛选 + LEFT JOIN admin_user
    @staticmethod
    async def list_audit_logs(
        action: str | None = None,
        target_type: str | None = None,
        admin_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """审计日志查询——LEFT JOIN AdminUser 获取 admin_username（一次查询，
        非分页后二次查询）；日期参数由 Router 解析为 datetime（start 00:00 /
        end 23:59:59 UTC）后传入；返回 dict {total,page,page_size,items}。"""
        ...

    # ==================== 知识库管理 ====================

    @staticmethod
    async def create_category(name: str, code: str, admin_id: int, content: dict | None = None) -> dict:
        """创建知识分类。

        R12-Admin-2: name 或 code 任一重复均返回 409（原仅查 code、且直接插入
        触发 IntegrityError 500）；审计 changes 记 name+code，commit 后写入并传
        target_id=category.id（R9-Admin-P2-1）。
        """
        async with async_session_factory() as db:
            dup = await db.scalar(
                select(KnowledgeCategory).where(
                    or_(KnowledgeCategory.name == name, KnowledgeCategory.code == code)
                )
            )
            if dup:
                raise AppException("分类名称或编码已存在", 409)
            category = KnowledgeCategory(name=name, code=code, content=content or {})
            db.add(category)
            await db.commit()
            await db.refresh(category)
            await AdminService._write_audit_log(
                db, admin_id, "create", "knowledge", target_id=category.id,
                changes={"name": {"old": None, "new": name}, "code": {"old": None, "new": code}},
            )
            return {"id": category.id, "name": category.name, "code": category.code}

    @staticmethod
    async def update_category(category_id: int, name: str | None, content: dict | None, admin_id: int) -> dict:
        """更新知识分类——仅 name/content 可改（R4-Admin-11，code 不可改），
        commit + refresh 后审计。"""
        ...

    @staticmethod
    async def delete_category(category_id: int, admin_id: int) -> None:
        """删除知识分类——commit 后审计 {code: {old, new}}。"""
        ...

    @staticmethod
    async def create_rule(
        rule_id: str, rule_name: str, rule_type: str,
        condition: dict, diagnosis: dict,
        training_methods: list | None = None,
        training_plan_template: str | None = None,
        adjustment_action: str | None = None,
        admin_id: int = 0,
    ) -> dict:
        """创建知识规则——重复 rule_id 409；返回 {"id", "rule_id"}（R4-Admin-21）。"""
        ...

    # R4-Admin-13: 显式 is_active 参数；R12-Admin-4: rule_id 为 int 数据库 ID（主键）
    @staticmethod
    async def toggle_rule(rule_id: int, is_active: bool, admin_id: int) -> dict:
        """显式设置规则状态——按 RuleDefinition.id 主键查询；审计 changes 为
        {is_active: {old,new}}（R12-Admin-5）；返回 {"id", "is_active"}。"""
        ...

    # ==================== 模型版本 ====================

    @staticmethod
    async def activate_model_version(version_id: str, admin_id: int) -> dict:
        """激活模型版本——S6 阶段仅记录审计日志（端点已注释，Phase 2 占位）。"""
        ...
```

---

## 5.3 审计日志清理 Celery Task

```python
# app/tasks/audit.py
# R13-P3 文档同步: 实际文件为 app/tasks/audit.py（非 audit_beat.py），
# 任务名 app.tasks.audit.cleanup_old_logs（非 audit.cleanup_old_logs），
# 使用 @shared_task + async_session_factory，返回清理统计 dict。
"""Celery tasks — 审计日志

R12-Admin-3/BeatTasks-2: 补齐实现（原 TODO 空壳 + 保留期口径错误）。
依据：数据库详细设计 §审计日志保留策略 — PIPL 合规保留期 3 年（1095 天），
超期记录由 Celery Beat 定期清理（原 TODO 写 180 天口径错误，已按设计修正为 3 年）。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)

# PIPL 合规保留期：3 年
AUDIT_LOG_RETENTION_DAYS = 365 * 3


@shared_task(name="app.tasks.audit.cleanup_old_logs")
def cleanup_old_logs():
    """清理超期审计日志（每日 03:00）

    保留策略：PIPL 审计日志保留不少于 3 年（1095 天），超期记录删除。
    幂等：基于 WHERE created_at < cutoff 条件，重复执行无副作用。
    """
    logger.info("Running audit.cleanup_old_logs")

    async def _run():
        from sqlalchemy import delete

        from app.core.database import async_session_factory
        from app.models.admin import AuditLog

        cutoff = datetime.now(timezone.utc) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
        async with async_session_factory() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff)
            )
            await db.commit()
            return result.rowcount or 0

    deleted = asyncio.run(_run())
    logger.info(
        "audit_logs_cleaned",
        extra={"deleted": deleted, "retention_days": AUDIT_LOG_RETENTION_DAYS},
    )
    return {"status": "ok", "deleted": deleted, "retention_days": AUDIT_LOG_RETENTION_DAYS}


# Beat 注册（app/core/beat_schedule.py）：
#   "audit-log-cleanup": {
#       "task": "app.tasks.audit.cleanup_old_logs",
#       "schedule": crontab(minute=0, hour=3),  # 每天 03:00
#       "options": {"queue": "infra"},
#   }
```

---

## 6. API 路由实现

```python
# app/api/v1/admin/router.py
"""管理后台 API 路由。"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_admin_session, require_super_admin, require_model_admin
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.schemas.admin import (
    AdminLoginRequest, AdminLoginResponse,
    ConfigCreateRequest, ConfigUpdateRequest,
    UserBanRequest,
    CategoryCreateRequest, CategoryUpdateRequest,
    RuleCreateRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["管理后台"])

# R13-P3 文档同步（Admin-8）: 装饰器顺序统一为 @router.xxx() 在上、
# @limiter.limit() 紧随其下（slowapi 要求，反幻觉约束已明确）；
# 限流值使用 RateLimits.DEFAULT（= "100/minute"），登录端点为 "5/minute"；
# 所有端点带 request: Request 参数（slowapi 依赖注入）；
# 认证依赖为 get_admin_session / require_super_admin（返回 session dict），
# 业务调用取 session["admin_id"]。


# ==================== Admin 登录/登出 ====================

@router.post("/login", summary="管理员登录")
@limiter.limit("5/minute")
async def admin_login(body: AdminLoginRequest, request: Request):
    """管理员登录（独立认证体系，不使用 JWT）"""
    data = await AdminService.login(body.username, body.password)
    return success(data=data)


@router.post("/logout", summary="管理员登出")
@limiter.limit(RateLimits.DEFAULT)
async def admin_logout(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """管理员登出——支持 "Admin xxx" / "Bearer xxx" 两种前缀（R5-Admin-4）"""
    auth = request.headers.get("authorization", "")
    parts = auth.split(" ", 1)
    token = parts[1] if len(parts) == 2 and parts[0] in ("Admin", "Bearer") else auth
    await AdminService.logout(token)
    return success(message="已登出")


# ==================== 用户管理 ====================

@router.get("/users", summary="用户列表查询")
@limiter.limit(RateLimits.DEFAULT)
async def list_users(
    request: Request,
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_admin_session),
):
    """用户列表查询（散参传 Service，非 Query 对象）"""
    data = await AdminService.list_users(status, q, page, page_size)
    return success(data=data)


@router.post("/users/{user_id}/ban", summary="封禁用户")
@limiter.limit(RateLimits.DEFAULT)
async def ban_user(
    user_id: int,
    body: UserBanRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """封禁用户（仅超级管理员）"""
    data = await AdminService.ban_user(user_id, body.reason, session["admin_id"])
    return success(data=data, message="用户已封禁")


@router.post("/users/{user_id}/unban", summary="解禁用户")
@limiter.limit(RateLimits.DEFAULT)
async def unban_user(
    user_id: int,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """解禁用户（仅超级管理员）"""
    data = await AdminService.unban_user(user_id, session["admin_id"])
    return success(data=data, message="用户已解禁")


# ==================== 系统配置 ====================

@router.get("/configs", summary="配置列表")
@limiter.limit(RateLimits.DEFAULT)
async def list_configs(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    data = await AdminService.list_configs()
    return success(data=data)


@router.get("/configs/{key}", summary="获取单个配置")
@limiter.limit(RateLimits.DEFAULT)
async def get_config(
    key: str,
    request: Request,
    session: dict = Depends(get_admin_session),
):
    data = await AdminService.get_config(key)
    return success(data=data)


@router.post("/configs", summary="创建配置")
@limiter.limit(RateLimits.DEFAULT)
async def create_config(
    body: ConfigCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建配置（仅超级管理员）——字段 config_key/config_value（R4-Admin-19）"""
    data = await AdminService.create_config(
        body.config_key, body.config_value, body.description, session["admin_id"],
    )
    return success(data=data, message="配置已创建")


@router.patch("/configs/{key}", summary="更新配置")
@limiter.limit(RateLimits.DEFAULT)
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """更新配置（仅超级管理员）——DEL config:{key} 缓存失效"""
    data = await AdminService.update_config(
        key, body.config_value, body.description, session["admin_id"],
    )
    return success(data=data, message="配置已更新")


@router.delete("/configs/{key}", summary="删除配置")
@limiter.limit(RateLimits.DEFAULT)
async def delete_config(
    key: str,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """删除配置（仅超级管理员）"""
    await AdminService.delete_config(key, session["admin_id"])
    return success(message="配置已删除")


# ==================== 审计日志 ====================

# R13-P3 文档同步: start_date/end_date 由 Router 解析为 UTC datetime
# （start 00:00:00 / end 23:59:59），非法格式降级为 None（不报错）
@router.get("/audit-logs", summary="审计日志查询")
@limiter.limit(RateLimits.DEFAULT)
async def list_audit_logs(
    request: Request,
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    admin_id: int | None = Query(default=None, description="按管理员 ID 筛选"),
    start_date: str | None = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_admin_session),
):
    """审计日志查询（支持管理员/时间段筛选）"""
    from datetime import datetime, timezone

    start_dt = (
        datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        if start_date else None
    )
    end_dt = (
        datetime.fromisoformat(end_date).replace(
            tzinfo=timezone.utc, hour=23, minute=59, second=59
        )
        if end_date else None
    )
    data = await AdminService.list_audit_logs(
        action, target_type, admin_id, start_dt, end_dt, page, page_size,
    )
    return success(data=data)


# ==================== 知识库管理 ====================

@router.post("/knowledge/categories", summary="创建知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def create_category(
    body: CategoryCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建知识分类（超级管理员）——name/code 重复 409（R12-Admin-2）"""
    data = await AdminService.create_category(
        body.name, body.code, session["admin_id"], body.content,
    )
    return success(data=data, message="分类已创建")


# R4-Admin-11: 仅允许更新 name 和 content（不允许更新 code）
@router.patch("/knowledge/categories/{category_id}", summary="更新知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """更新知识分类（超级管理员，仅 name/content 可改）"""
    data = await AdminService.update_category(
        category_id, body.name, body.content, session["admin_id"],
    )
    return success(data=data, message="分类已更新")


@router.delete("/knowledge/categories/{category_id}", summary="删除知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def delete_category(
    category_id: int,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """删除知识分类（超级管理员）"""
    await AdminService.delete_category(category_id, session["admin_id"])
    return success(message="分类已删除")


@router.post("/knowledge/rules", summary="创建知识规则")
@limiter.limit(RateLimits.DEFAULT)
async def create_rule(
    body: RuleCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建知识规则（超级管理员）——重复 rule_id 409"""
    data = await AdminService.create_rule(
        body.rule_id, body.rule_name, body.rule_type,
        body.condition, body.diagnosis,
        body.training_methods, body.training_plan_template,
        body.adjustment_action,
        session["admin_id"],
    )
    return success(data=data, message="规则已创建")


# R12-Admin-4: rule_id 为 int 数据库 ID（对齐 API §19.5.5 参数表）；
# is_active 显式参数（R4-Admin-13）
@router.patch("/knowledge/rules/{rule_id}/toggle", summary="设置知识规则状态")
@limiter.limit(RateLimits.DEFAULT)
async def toggle_rule(
    rule_id: int,
    request: Request,
    is_active: bool = Query(..., description="目标状态 true=启用/false=禁用"),
    session: dict = Depends(require_super_admin),
):
    """设置知识规则状态（超级管理员，显式 is_active 参数）"""
    data = await AdminService.toggle_rule(rule_id, is_active, session["admin_id"])
    return success(data=data, message="规则状态已更新")


# ==================== 模型版本管理 ====================

# R4-Admin-23: activate_model_version 注释掉（Phase 2 占位，S7+ 实现）
# @router.post("/model-versions/{version_id}/activate", summary="激活模型版本")
# @limiter.limit(RateLimits.DEFAULT)
# async def activate_model_version(
#     version_id: str,
#     request: Request,
#     session: dict = Depends(require_model_admin),
# ):
#     data = await AdminService.activate_model_version(version_id, session["admin_id"])
#     return success(data=data, message="模型版本已激活")
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.admin.router import router as admin_router
api_router.include_router(admin_router)
```

---

## 7. 测试要点

```python
# tests/unit/test_admin.py
# R13-P3 文档同步: 样例与实际测试一致——pwd_context 创建管理员、
# client fixture 走 HTTP 端点、Service 散参签名（user_id 在前）。
"""admin 模块测试。覆盖：管理员认证、用户管理、系统配置热更新、审计日志、知识库 CRUD、权限控制。"""
import pytest
import pytest_asyncio
from app.core.security import pwd_context
from app.services.admin_service import AdminService, ADMIN_SESSION_PREFIX
from app.models.admin import AdminUser


@pytest_asyncio.fixture(scope="function")
async def admin_in_db(db_session):
    """创建测试管理员（passlib bcrypt 哈希）。"""
    admin = AdminUser(
        username="test_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture(scope="function")
async def admin_token(admin_in_db):
    """获取 admin session token。"""
    data = await AdminService.login("test_admin", "Admin@123")
    return data.session_token


@pytest_asyncio.fixture(scope="function")
async def admin_headers(admin_token):
    """admin 认证 headers。"""
    return {"Authorization": f"Bearer {admin_token}"}


# === 1. 管理员认证 ===
@pytest.mark.asyncio
class TestAdminAuth:
    async def test_login_success(self, client, admin_in_db):
        """登录成功：token + role + expires_in=1800。"""
        data = await AdminService.login("test_admin", "Admin@123")
        assert data.session_token
        assert data.admin.role == "super_admin"
        assert data.expires_in == 1800

    async def test_login_wrong_password(self, client, admin_in_db):
        """密码错误 401。"""
        from app.core.exceptions import AppException
        with pytest.raises(AppException) as exc_info:
            await AdminService.login("test_admin", "wrong_password")
        assert exc_info.value.status_code == 401

    async def test_login_disabled_admin(self, db_session, admin_in_db):
        """已禁用管理员登录 403。"""
        from app.core.exceptions import AppException
        admin_in_db.is_active = False
        await db_session.commit()
        with pytest.raises(AppException) as exc_info:
            await AdminService.login("test_admin", "Admin@123")
        assert exc_info.value.status_code == 403

    async def test_logout(self, admin_headers, admin_token):
        """登出后 session 删除（redis exists == 0）。"""
        from app.core.redis import get_redis
        await AdminService.logout(admin_token)
        redis = await get_redis()
        assert await redis.exists(f"{ADMIN_SESSION_PREFIX}{admin_token}") == 0


# === 2. 用户管理（Service 签名 user_id 在前）===
@pytest.mark.asyncio
async def test_ban_user(client, admin_headers, test_user):
    """封禁用户。"""
    resp = await client.post(
        f"/api/v1/admin/users/{test_user.id}/ban",
        json={"reason": "违规操作"},
        headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ban_already_banned(client, admin_headers, test_user):
    """重复封禁 409。"""
    # 先 ban 一次再 ban 第二次 → resp.status_code == 409
    ...


# === 3. 系统配置热更新 ===
# 实际测试通过 HTTP 端点创建/更新/删除配置（configs CRUD 5 个测试），
# 断言 config_value 更新生效与 404/409 行为


# === 4. 审计日志 ===
# R12-Admin-12: 审计筛选参数测试位于 tests/unit/test_supplements_p2.py
# TestAdminAuditLogFilters（action/target_type/admin_id/时间段/分页 + admin_username JOIN）
# R12-Admin-13: session 滑动续期测试位于同文件 TestAdminSessionRenewal
# （压缩 TTL → 认证请求 → TTL 回 1800；登出后再访问 401）


# === 5. 知识库 CRUD ===
# R12-Admin-2: 重复 name/code 创建分类 409 测试位于 tests/unit/test_supplements_p1.py
# TestAdminCreateCategoryConflict（重复 name / 重复 code / name+code 均重复 → 409，
# 不同 name+code → 200）


# === 6. 权限控制 ===
@pytest.mark.asyncio
class TestAdminPermission:
    async def test_admin_endpoints_without_token(self, client):
        """无 token 访问 admin 端点 401。"""
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    async def test_content_admin_cannot_ban(self, client, content_admin_token, test_user):
        """内容管理员不能封禁用户（仅超级管理员）→ 403。"""
        ...
```

**R12 修复回归测试位置**（R13-P3 文档同步汇总）：
- Admin-1（每请求 is_active 校验）：`app/core/deps.py` get_admin_session + supplements_p2 会话失效路径
- Admin-2（create_category 409）：`tests/unit/test_supplements_p1.py` TestAdminCreateCategoryConflict
- Admin-3（审计 3 年保留）：`app/tasks/audit.py` 实现 + `app/core/beat_schedule.py` 注册
- Admin-12/13（审计筛选/续期）：`tests/unit/test_supplements_p2.py` L1370-1518

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_admin.py -v`
- [ ] 管理员认证独立于普通用户（AdminUser 表，不使用 JWT）
- [ ] 密码使用 bcrypt 验证
- [ ] session 存储在 Redis（30min 过期，请求时续期）
- [ ] 用户封禁/解禁操作正确更新 user.status
- [ ] 所有管理操作写入 audit_log（changes JSONB {field:{old,new}}）
- [ ] 审计日志写入失败不阻塞主操作
- [ ] 系统配置修改后 Redis 缓存被清除（DEL config:{key}）
- [ ] 系统配置读取时 Redis 缓存优先，未命中回填
- [ ] 知识库 CRUD 操作正确更新对应表
- [ ] super_admin 权限守卫正确拦截非超级管理员请求
- [ ] Model 已在 `app/models/__init__.py` 中导入
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- 管理员认证 **必须** 独立于普通用户 JWT，使用 AdminUser 表 + Redis session，**禁止** 复用 JWT 体系
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 所有管理操作 **必须** 写入 audit_log，**禁止** 遗漏审计
- 审计日志写入失败 **必须** 不阻塞主操作，**禁止** 因审计失败而回滚业务
- 系统配置更新后 **必须** 清除 Redis 缓存，**禁止** 让旧缓存残留
- 密码 **必须** 使用 bcrypt 存储，**禁止** 明文存储
- 封禁/解禁操作 **必须** 校验当前状态，**禁止** 重复操作
- super_admin 权限操作 **必须** 使用 `require_super_admin` 守卫，**禁止** 跳过权限校验
- 所有 API 端点 **必须** 添加 `@limiter.limit()` 限流装饰器，**禁止** 裸露无限流路由
- 管理员登录端点 **必须** 使用 `@limiter.limit("5/minute")` 严格限流，**禁止** 使用默认 100/minute
- 装饰器顺序 **必须** 为 `@router.xxx()` 在上、`@limiter.limit()` 紧随其下（slowapi 要求限流装饰器贴近路由函数；放在 `@router.xxx()` 上方会注册未限流的原始函数、限流不生效，R12 已统一全 app 95 端点装饰器顺序），**禁止** 颠倒装饰器顺序
- 路由文件 **必须** 导入 `from app.core.limiter import limiter`，**禁止** 遗漏导入

> **覆盖度修复说明（A-8 / X-16）**：
> - A-8：`AdminLoginResponse.admin` 字段类型已从字符串引用 `"AdminBrief"` 修正为直接类型引用 `AdminBrief`。
> - X-16：已解决。架构 §4.1 已对齐，Phase 1 暴露管理 API 为正式设计决策，RBAC 角色守卫（get_current_admin / require_super_admin）替代 Phase 守卫。
