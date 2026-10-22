# admin 基础设施模块 — 后端垂直切片设计

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

from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.core.pagination import Paginated


# --- 认证 Schema ---
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    session_token: [REDACTED]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
    admin: AdminBrief
    expires_in: int = 1800  # 30 分钟


class AdminBrief(BaseModel):
    id: int
    username: str
    role: str
    model_config = {"from_attributes": True}


# --- 用户管理 Schema ---
class UserManageBrief(BaseModel):
    id: int
    nickname: str
    phone: Optional[str] = None
    openid: Optional[str] = None
    status: str
    created_at: datetime


class UserBanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class UserListQuery(BaseModel):
    status: Optional[str] = None
    q: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


PaginatedUsers = Paginated[UserManageBrief]


# --- 系统配置 Schema ---
class ConfigCreateRequest(BaseModel):
    config_key: str = Field(..., min_length=1, max_length=64)
    config_value: Any
    description: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    config_value: Any
    description: Optional[str] = None


class ConfigBrief(BaseModel):
    id: int
    config_key: str
    config_value: Any
    description: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


# --- 审计日志 Schema ---
class AuditLogBrief(BaseModel):
    id: int
    admin_id: int
    admin_username: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[int] = None
    changes: Optional[dict] = None
    created_at: datetime


class AuditLogQuery(BaseModel):
    admin_id: Optional[int] = None
    action: Optional[str] = None
    target_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


PaginatedAuditLogs = Paginated[AuditLogBrief]


# --- 知识库管理 Schema ---
class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=32)
    content: dict


class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    content: Optional[dict] = None


class RuleCreateRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=64)
    rule_name: str = Field(..., min_length=1, max_length=128)
    rule_type: str = Field(..., min_length=1, max_length=32)
    condition: dict
    diagnosis: dict
    training_methods: Optional[list] = None
    training_plan_template: Optional[str] = None
    adjustment_action: Optional[str] = None
```

---

## 5. Service 实现

### 5.1 管理员认证依赖

```python
# app/core/admin_deps.py
"""管理员认证依赖——独立于普通用户 JWT 体系。"""

import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header
from sqlalchemy import select

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.database import get_async_session
from app.models.admin import AdminUser

# Session TTL
ADMIN_SESSION_TTL = 1800  # 30 分钟


async def get_current_admin(
    authorization: str = Header(..., description="Admin session token"),
) -> AdminUser:
    """从 session token 获取管理员——不使用 JWT。

    流程：
    1. 从 header 提取 session token
    2. Redis 查询 session → admin_id
    3. 加载 AdminUser
    4. 校验 is_active
    """
    if not authorization.startswith("Admin "):
        raise AppException("管理员认证失败", 401)

    token = authorization[6:]  # 去掉 "Admin " 前缀

    redis = await get_redis()
    admin_id = await redis.get(f"admin:session:{token}")
    if not admin_id:
        raise AppException("管理员 session 已过期，请重新登录", 401)

    async with get_async_session() as db:
        admin = await db.scalar(
            select(AdminUser).where(AdminUser.id == int(admin_id))
        )
        if not admin:
            raise AppException("管理员账号不存在", 401)
        if not admin.is_active:
            raise AppException("管理员账号已禁用", 403)

        # 续期 session
        await redis.expire(f"admin:session:{token}", ADMIN_SESSION_TTL)
        return admin


async def require_super_admin(
    admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """要求超级管理员权限。"""
    if admin.role != "super_admin":
        raise AppException("需要超级管理员权限", 403)
    return admin
```

### 5.2 Admin Service

```python
# app/services/admin_service.py
"""管理后台业务逻辑层。"""

import secrets
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from sqlalchemy import select, update

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.database import get_async_session
from app.core.pagination import paginate
from app.models.admin import AdminUser, AuditLog, SystemConfig
from app.models.user import User
from app.models.knowledge_base import (
    KnowledgeCategory, KnowledgeEntry,
    RuleDefinition, TrainingTemplate,
)
from app.schemas.admin import (
    AdminBrief, AdminLoginResponse,
    UserManageBrief, UserListQuery, PaginatedUsers,
    ConfigBrief, ConfigCreateRequest, ConfigUpdateRequest,
    AuditLogBrief, AuditLogQuery, PaginatedAuditLogs,
    CategoryCreateRequest, CategoryUpdateRequest,
    RuleCreateRequest,
)


class AdminService:
    """管理后台业务逻辑层。"""

    # Session TTL
    SESSION_TTL = 1800  # 30 分钟

    # --- 管理员认证 ---

    @staticmethod
    async def login(username: str, password: str) -> AdminLoginResponse:
        """管理员登录——用户名+密码（bcrypt 验证），签发 session。

        不使用 JWT，session 存储在 Redis（30min 过期）。
        """
        async with get_async_session() as db:
            admin = await db.scalar(
                select(AdminUser).where(AdminUser.username == username)
            )
            if not admin:
                raise AppException("用户名或密码错误", 401)
            if not admin.is_active:
                raise AppException("管理员账号已禁用", 403)

            # bcrypt 验证
            if not bcrypt.checkpw(
                password.encode("utf-8"), admin.password_hash.encode("utf-8")
            ):
                raise AppException("用户名或密码错误", 401)

            # 签发 session（随机 token，存 Redis）
            session_token = secrets.token_urlsafe(32)
            redis = await get_redis()
            await redis.setex(
                f"admin:session:{session_token}",
                AdminService.SESSION_TTL,
                str(admin.id),
            )

            return AdminLoginResponse(
                session_token=session_token,
                admin=AdminBrief.model_validate(admin),
                expires_in=AdminService.SESSION_TTL,
            )

    @staticmethod
    async def logout(session_token: str) -> None:
        """管理员登出——删除 Redis session。"""
        redis = await get_redis()
        await redis.delete(f"admin:session:{session_token}")

    # --- 审计日志 ---

    @staticmethod
    async def _write_audit_log(
        admin_id: int,
        action: str,
        target_type: str,
        target_id: Optional[int] = None,
        changes: Optional[dict] = None,
    ) -> None:
        """写入审计日志——所有管理操作必须调用。

        changes 格式: {field: {old, new}}
        审计日志写入失败 → 记录错误日志，不阻塞主操作。
        """
        try:
            async with get_async_session() as db:
                log = AuditLog(
                    admin_id=admin_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    changes=changes,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                f"Audit log write failed: {e}"
            )

    # --- 用户管理 ---

    @staticmethod
    async def list_users(query: UserListQuery) -> PaginatedUsers:
        """用户列表查询。"""
        async with get_async_session() as db:
            stmt = select(User)
            if query.status:
                stmt = stmt.where(User.status == query.status)
            if query.q:
                stmt = stmt.where(
                    User.nickname.ilike(f"%{query.q}%") |
                    User.phone.ilike(f"%{query.q}%")
                )
            stmt = stmt.order_by(User.created_at.desc())

            total, items = await paginate(db, stmt, query.page, query.page_size)
            return PaginatedUsers(
                total=total, page=query.page, page_size=query.page_size,
                items=[UserManageBrief.model_validate(u) for u in items],
            )

    @staticmethod
    async def ban_user(
        admin_id: int,
        user_id: int,
        reason: str,
    ) -> dict:
        """封禁用户——更新 user.status='banned'。"""
        async with get_async_session() as db:
            user = await db.scalar(select(User).where(User.id == user_id))
            if not user:
                raise AppException("用户不存在", 404)
            if user.status == "banned":
                raise AppException("用户已被封禁", 409)

            old_status = user.status
            user.status = "banned"
            await db.commit()

            # 审计日志
            await AdminService._write_audit_log(
                admin_id=admin_id,
                action="update",
                target_type="user",
                target_id=user_id,
                changes={"status": {"old": old_status, "new": "banned"},
                         "ban_reason": {"old": None, "new": reason}},
            )

            return {"user_id": user_id, "status": "banned", "reason": reason}

    @staticmethod
    async def unban_user(admin_id: int, user_id: int) -> dict:
        """解禁用户——更新 user.status='active'。"""
        async with get_async_session() as db:
            user = await db.scalar(select(User).where(User.id == user_id))
            if not user:
                raise AppException("用户不存在", 404)
            if user.status != "banned":
                raise AppException("用户未被封禁", 409)

            old_status = user.status
            user.status = "active"
            await db.commit()

            await AdminService._write_audit_log(
                admin_id=admin_id,
                action="update",
                target_type="user",
                target_id=user_id,
                changes={"status": {"old": old_status, "new": "active"}},
            )

            return {"user_id": user_id, "status": "active"}

    # --- 系统配置管理 ---

    @staticmethod
    async def list_configs() -> list[ConfigBrief]:
        """查询所有系统配置。"""
        async with get_async_session() as db:
            result = await db.execute(
                select(SystemConfig).order_by(SystemConfig.config_key)
            )
            return [ConfigBrief.model_validate(c) for c in result.scalars()]

    @staticmethod
    async def get_config(key: str) -> ConfigBrief:
        """查询单个配置（Redis 缓存优先）。"""
        redis = await get_redis()
        cached = await redis.get(f"config:{key}")
        if cached:
            import json
            return ConfigBrief(
                id=0, config_key=key,
                config_value=json.loads(cached),
                description=None, updated_at=datetime.now(timezone.utc),
            )
        async with get_async_session() as db:
            config = await db.scalar(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
            if not config:
                raise AppException(f"配置 {key} 不存在", 404)
            # 回填缓存
            import json
            await redis.setex(
                f"config:{key}", 3600,
                json.dumps(config.config_value, ensure_ascii=False),
            )
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def create_config(
        admin_id: int,
        req: ConfigCreateRequest,
    ) -> ConfigBrief:
        """创建系统配置。"""
        async with get_async_session() as db:
            existing = await db.scalar(
                select(SystemConfig).where(SystemConfig.config_key == req.config_key)
            )
            if existing:
                raise AppException(f"配置 {req.config_key} 已存在", 409)

            config = SystemConfig(
                config_key=req.config_key,
                config_value=req.config_value,
                description=req.description,
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)

            await AdminService._write_audit_log(
                admin_id=admin_id, action="create",
                target_type="config", target_id=config.id,
                changes={"config_key": {"old": None, "new": req.config_key},
                         "config_value": {"old": None, "new": req.config_value}},
            )
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def update_config(
        admin_id: int,
        key: str,
        req: ConfigUpdateRequest,
    ) -> ConfigBrief:
        """更新系统配置——修改后 Redis DEL config:{key} 实现热更新。"""
        async with get_async_session() as db:
            config = await db.scalar(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
            if not config:
                raise AppException(f"配置 {key} 不存在", 404)

            old_value = config.config_value
            config.config_value = req.config_value
            if req.description is not None:
                config.description = req.description
            config.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(config)

            # 热更新：清除 Redis 缓存
            redis = await get_redis()
            await redis.delete(f"config:{key}")

            await AdminService._write_audit_log(
                admin_id=admin_id, action="update",
                target_type="config", target_id=config.id,
                changes={"config_value": {"old": old_value, "new": req.config_value}},
            )
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def delete_config(admin_id: int, key: str) -> None:
        """删除系统配置。"""
        async with get_async_session() as db:
            config = await db.scalar(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
            if not config:
                raise AppException(f"配置 {key} 不存在", 404)

            old_value = config.config_value
            await db.delete(config)
            await db.commit()

            # 清除缓存
            redis = await get_redis()
            await redis.delete(f"config:{key}")

            await AdminService._write_audit_log(
                admin_id=admin_id, action="delete",
                target_type="config", target_id=config.id,
                changes={"config_key": {"old": key, "new": None},
                         "config_value": {"old": old_value, "new": None}},
            )

    # --- 审计日志查询 ---

    @staticmethod
    async def list_audit_logs(query: AuditLogQuery) -> PaginatedAuditLogs:
        """审计日志查询——按管理员/操作类型/时间筛选。"""
        async with get_async_session() as db:
            stmt = select(AuditLog)
            if query.admin_id:
                stmt = stmt.where(AuditLog.admin_id == query.admin_id)
            if query.action:
                stmt = stmt.where(AuditLog.action == query.action)
            if query.target_type:
                stmt = stmt.where(AuditLog.target_type == query.target_type)
            if query.start_date:
                stmt = stmt.where(AuditLog.created_at >= query.start_date)
            if query.end_date:
                stmt = stmt.where(AuditLog.created_at <= query.end_date)
            stmt = stmt.order_by(AuditLog.created_at.desc())

            total, items = await paginate(db, stmt, query.page, query.page_size)

            # 关联查询管理员用户名
            admin_ids = {log.admin_id for log in items}
            admin_names = {}
            if admin_ids:
                admins = await db.scalars(
                    select(AdminUser).where(AdminUser.id.in_(admin_ids))
                )
                admin_names = {a.id: a.username for a in admins}

            return PaginatedAuditLogs(
                total=total, page=query.page, page_size=query.page_size,
                items=[
                    AuditLogBrief(
                        id=log.id, admin_id=log.admin_id,
                        admin_username=admin_names.get(log.admin_id),
                        action=log.action, target_type=log.target_type,
                        target_id=log.target_id, changes=log.changes,
                        created_at=log.created_at,
                    )
                    for log in items
                ],
            )

    # --- 知识库 CRUD ---

    @staticmethod
    async def create_category(
        admin_id: int, req: CategoryCreateRequest,
    ) -> dict:
        """创建知识库分类。"""
        async with get_async_session() as db:
            existing = await db.scalar(
                select(KnowledgeCategory).where(KnowledgeCategory.code == req.code)
            )
            if existing:
                raise AppException(f"分类编码 {req.code} 已存在", 409)

            cat = KnowledgeCategory(name=req.name, code=req.code, content=req.content)
            db.add(cat)
            await db.commit()
            await db.refresh(cat)

            await AdminService._write_audit_log(
                admin_id=admin_id, action="create",
                target_type="knowledge", target_id=cat.id,
                changes={"code": {"old": None, "new": req.code}},
            )
            return {"id": cat.id, "name": cat.name, "code": cat.code}

    @staticmethod
    async def update_category(
        admin_id: int, category_id: int, req: CategoryUpdateRequest,
    ) -> dict:
        """更新知识库分类。"""
        async with get_async_session() as db:
            cat = await db.get(KnowledgeCategory, category_id)
            if not cat:
                raise AppException("分类不存在", 404)

            changes = {}
            if req.name is not None:
                changes["name"] = {"old": cat.name, "new": req.name}
                cat.name = req.name
            if req.content is not None:
                changes["content"] = {"old": cat.content, "new": req.content}
                cat.content = req.content
            await db.commit()

            await AdminService._write_audit_log(
                admin_id=admin_id, action="update",
                target_type="knowledge", target_id=category_id,
                changes=changes,
            )
            return {"id": cat.id, "name": cat.name, "code": cat.code}

    @staticmethod
    async def delete_category(admin_id: int, category_id: int) -> None:
        """删除知识库分类（级联删除条目）。"""
        async with get_async_session() as db:
            cat = await db.get(KnowledgeCategory, category_id)
            if not cat:
                raise AppException("分类不存在", 404)

            code = cat.code
            await db.delete(cat)
            await db.commit()

            await AdminService._write_audit_log(
                admin_id=admin_id, action="delete",
                target_type="knowledge", target_id=category_id,
                changes={"code": {"old": code, "new": None}},
            )

    @staticmethod
    async def create_rule(admin_id: int, req: RuleCreateRequest) -> dict:
        """创建规则定义。"""
        async with get_async_session() as db:
            existing = await db.scalar(
                select(RuleDefinition).where(RuleDefinition.rule_id == req.rule_id)
            )
            if existing:
                raise AppException(f"规则 {req.rule_id} 已存在", 409)

            rule = RuleDefinition(
                rule_id=req.rule_id, rule_name=req.rule_name,
                rule_type=req.rule_type, condition=req.condition,
                diagnosis=req.diagnosis,
                training_methods=req.training_methods,
                training_plan_template=req.training_plan_template,
                adjustment_action=req.adjustment_action,
            )
            db.add(rule)
            await db.commit()
            await db.refresh(rule)

            await AdminService._write_audit_log(
                admin_id=admin_id, action="create",
                target_type="knowledge", target_id=rule.id,
                changes={"rule_id": {"old": None, "new": req.rule_id}},
            )
            return {"id": rule.id, "rule_id": rule.rule_id}

    @staticmethod
    async def toggle_rule(admin_id: int, rule_id: int, is_active: bool) -> dict:
        """启用/禁用规则。"""
        async with get_async_session() as db:
            rule = await db.get(RuleDefinition, rule_id)
            if not rule:
                raise AppException("规则不存在", 404)

            old_active = rule.is_active
            rule.is_active = is_active
            await db.commit()

            await AdminService._write_audit_log(
                admin_id=admin_id, action="update",
                target_type="knowledge", target_id=rule_id,
                changes={"is_active": {"old": old_active, "new": is_active}},
            )
            return {"id": rule.id, "is_active": is_active}
```

---

## 5.3 审计日志清理 Celery Task

```python
# app/tasks/audit_beat.py
"""审计日志定时清理任务。"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from app.core.celery import celery_app
from app.core.database import get_async_session
from app.models.admin import AuditLog


@celery_app.task(name="audit.cleanup_old_logs")
def cleanup_old_logs_task():
    """审计日志自动清理——每日 03:00 执行。

    规则：
    1. 清理 3 年前的审计日志记录（DELETE FROM audit_log WHERE created_at < now() - 3 years）
    2. 保留 PIPL 合规所需的最近 3 年审计日志
    3. 幂等设计：基于 WHERE 条件删除，重复执行无副作用

    Beat 注册：见 beat_schedule.py 中 "audit-log-cleanup" 条目。
    """
    import asyncio
    asyncio.run(_cleanup_old_logs_async())


async def _cleanup_old_logs_async():
    """审计日志清理异步实现。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * 3)

    async with get_async_session() as db:
        await db.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await db.commit()
```

---

## 6. API 路由实现

```python
# app/api/v1/admin/router.py
"""管理后台 API 路由。"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.admin_deps import get_current_admin, require_super_admin
from app.core.limiter import limiter
from app.core.response import success
from app.models.admin import AdminUser
from app.schemas.admin import (
    AdminLoginRequest, AdminLoginResponse,
    UserListQuery, UserBanRequest,
    ConfigCreateRequest, ConfigUpdateRequest,
    AuditLogQuery,
    CategoryCreateRequest, CategoryUpdateRequest,
    RuleCreateRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["管理后台"])


# --- 认证 ---
@limiter.limit("5/minute")
@router.post("/login", summary="管理员登录")
async def admin_login(body: AdminLoginRequest):
    """管理员登录——用户名+密码，签发 session（不使用 JWT）。"""
    data = await AdminService.login(body.username, body.password)
    return success(data=data, message="登录成功")


@limiter.limit("100/minute")
@router.post("/logout", summary="管理员登出")
async def admin_logout(
    authorization: str = Depends(lambda: None),
    admin: AdminUser = Depends(get_current_admin),
):
    """管理员登出——删除 Redis session。"""
    token = authorization[6:] if authorization.startswith("Admin ") else ""
    await AdminService.logout(token)
    return success(message="登出成功")


# --- 用户管理 ---
@limiter.limit("100/minute")
@router.get("/users", summary="用户列表")
async def list_users(
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
):
    query = UserListQuery(status=status, q=q, page=page, page_size=page_size)
    data = await AdminService.list_users(query)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/users/{user_id}/ban", summary="封禁用户")
async def ban_user(
    user_id: int,
    body: UserBanRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.ban_user(admin.id, user_id, body.reason)
    return success(data=data, message="用户已封禁")


@limiter.limit("100/minute")
@router.post("/users/{user_id}/unban", summary="解禁用户")
async def unban_user(
    user_id: int,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.unban_user(admin.id, user_id)
    return success(data=data, message="用户已解禁")


# --- 系统配置管理 ---
@limiter.limit("100/minute")
@router.get("/configs", summary="配置列表")
async def list_configs(
    admin: AdminUser = Depends(get_current_admin),
):
    data = await AdminService.list_configs()
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/configs/{key}", summary="查询配置")
async def get_config(
    key: str,
    admin: AdminUser = Depends(get_current_admin),
):
    data = await AdminService.get_config(key)
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/configs", summary="创建配置")
async def create_config(
    body: ConfigCreateRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.create_config(admin.id, body)
    return success(data=data, message="配置已创建")


@limiter.limit("100/minute")
@router.patch("/configs/{key}", summary="更新配置")
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.update_config(admin.id, key, body)
    return success(data=data, message="配置已更新，缓存已刷新")


@limiter.limit("100/minute")
@router.delete("/configs/{key}", summary="删除配置")
async def delete_config(
    key: str,
    admin: AdminUser = Depends(require_super_admin),
):
    await AdminService.delete_config(admin.id, key)
    return success(message="配置已删除")


# --- 审计日志 ---
@limiter.limit("100/minute")
@router.get("/audit-logs", summary="审计日志查询")
async def list_audit_logs(
    admin_id: Optional[int] = Query(default=None),
    action: Optional[str] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
):
    query = AuditLogQuery(
        admin_id=admin_id, action=action, target_type=target_type,
        start_date=start_date, end_date=end_date,
        page=page, page_size=page_size,
    )
    data = await AdminService.list_audit_logs(query)
    return success(data=data)


# --- 知识库管理 ---
@limiter.limit("100/minute")
@router.post("/knowledge/categories", summary="创建分类")
async def create_category(
    body: CategoryCreateRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.create_category(admin.id, body)
    return success(data=data, message="分类已创建")


@limiter.limit("100/minute")
@router.patch("/knowledge/categories/{category_id}", summary="更新分类")
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.update_category(admin.id, category_id, body)
    return success(data=data, message="分类已更新")


@limiter.limit("100/minute")
@router.delete("/knowledge/categories/{category_id}", summary="删除分类")
async def delete_category(
    category_id: int,
    admin: AdminUser = Depends(require_super_admin),
):
    await AdminService.delete_category(admin.id, category_id)
    return success(message="分类已删除")


@limiter.limit("100/minute")
@router.post("/knowledge/rules", summary="创建规则")
async def create_rule(
    body: RuleCreateRequest,
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.create_rule(admin.id, body)
    return success(data=data, message="规则已创建")


@limiter.limit("100/minute")
@router.patch("/knowledge/rules/{rule_id}/toggle", summary="启用/禁用规则")
async def toggle_rule(
    rule_id: int,
    is_active: bool = Query(...),
    admin: AdminUser = Depends(require_super_admin),
):
    data = await AdminService.toggle_rule(admin.id, rule_id, is_active)
    return success(data=data, message="规则状态已更新")


# ===== Phase 2+ 占位端点（暂不实现，预留接口） =====

# @limiter.limit("100/minute")
# @router.post("/model-versions/{version_id}/activate", summary="激活模型版本")
# async def activate_model_version(
#     version_id: int,
#     admin: AdminUser = Depends(require_super_admin),
# ):
#     """激活指定模型版本，用于 AI 模型版本管理（Phase 2+）。
#     切换推理服务使用的模型版本，支持灰度发布和 A/B 测试。"""
#     data = await AdminService.activate_model_version(admin.id, version_id)
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
"""admin 模块测试。覆盖：管理员认证、用户管理、系统配置热更新、审计日志、知识库 CRUD。"""
import pytest
import bcrypt
from unittest.mock import AsyncMock, patch
from app.services.admin_service import AdminService
from app.core.exceptions import AppException


@pytest.fixture
async def admin_user(db_session):
    """创建测试管理员。"""
    from app.models.admin import AdminUser
    password_hash = bcrypt.hashpw("test123".encode(), bcrypt.gensalt()).decode()
    admin = AdminUser(
        username="test_admin",
        password_hash=password_hash,
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


# === 1. 管理员认证 ===
@pytest.mark.asyncio
async def test_login_success(db_session, admin_user, mock_redis):
    """管理员登录成功，返回 session token。"""
    mock_redis.setex = AsyncMock()
    result = await AdminService.login("test_admin", "test123")
    assert "session_token" in result.model_dump()
    assert result.admin.username == "test_admin"


@pytest.mark.asyncio
async def test_login_wrong_password(db_session, admin_user):
    """密码错误返回 401。"""
    with pytest.raises(AppException) as exc:
        await AdminService.login("test_admin", "wrong_password")
    assert exc.value.code == 401


@pytest.mark.asyncio
async def test_login_disabled_admin(db_session, admin_user):
    """已禁用管理员返回 403。"""
    admin_user.is_active = False
    await db_session.commit()
    with pytest.raises(AppException) as exc:
        await AdminService.login("test_admin", "test123")
    assert exc.value.code == 403


# === 2. 用户管理 ===
@pytest.mark.asyncio
async def test_ban_user(db_session, admin_user):
    """封禁用户正确更新 status。"""
    from app.models.user import User
    user = User(nickname="testuser", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await AdminService.ban_user(admin_user.id, user.id, "违规操作")
    assert result["status"] == "banned"

    await db_session.refresh(user)
    assert user.status == "banned"


@pytest.mark.asyncio
async def test_ban_already_banned(db_session, admin_user):
    """重复封禁返回 409。"""
    from app.models.user import User
    user = User(nickname="testuser", status="banned")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    with pytest.raises(AppException) as exc:
        await AdminService.ban_user(admin_user.id, user.id, "违规")
    assert exc.value.code == 409


# === 3. 系统配置热更新 ===
@pytest.mark.asyncio
async def test_update_config_clears_cache(db_session, admin_user, mock_redis):
    """配置更新后 Redis 缓存被清除。"""
    from app.models.admin import SystemConfig
    config = SystemConfig(config_key="test_key", config_value={"limit": 3})
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    mock_redis.delete = AsyncMock()
    await AdminService.update_config(
        admin_user.id, "test_key",
        type("R", (), {"config_value": {"limit": 5}})(),
    )
    mock_redis.delete.assert_called_with("config:test_key")


# === 4. 审计日志 ===
@pytest.mark.asyncio
async def test_audit_log_written(db_session, admin_user):
    """封禁用户操作写入审计日志。"""
    from app.models.admin import AuditLog
    from app.models.user import User
    from sqlalchemy import select

    user = User(nickname="testuser", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    await AdminService.ban_user(admin_user.id, user.id, "测试封禁")

    # 验证审计日志
    logs = await db_session.scalars(
        select(AuditLog).where(AuditLog.target_type == "user")
    )
    log_list = list(logs)
    assert len(log_list) > 0
    assert log_list[-1].action == "update"
    assert log_list[-1].changes["status"]["new"] == "banned"


# === 5. 知识库 CRUD ===
@pytest.mark.asyncio
async def test_create_category(db_session, admin_user):
    """创建知识库分类。"""
    from app.schemas.admin import CategoryCreateRequest
    req = CategoryCreateRequest(
        name="测试分类", code="test_cat", content={"desc": "测试"}
    )
    result = await AdminService.create_category(admin_user.id, req)
    assert result["code"] == "test_cat"


@pytest.mark.asyncio
async def test_duplicate_category_code(db_session, admin_user):
    """重复分类编码返回 409。"""
    from app.models.knowledge_base import KnowledgeCategory
    from app.schemas.admin import CategoryCreateRequest

    cat = KnowledgeCategory(name="已有分类", code="dup_code", content={})
    db_session.add(cat)
    await db_session.commit()

    req = CategoryCreateRequest(
        name="新分类", code="dup_code", content={}
    )
    with pytest.raises(AppException) as exc:
        await AdminService.create_category(admin_user.id, req)
    assert exc.value.code == 409
```

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
- `@limiter.limit()` 装饰器 **必须** 位于 `@router.xxx()` 装饰器上方，**禁止** 颠倒装饰器顺序
- 路由文件 **必须** 导入 `from app.core.limiter import limiter`，**禁止** 遗漏导入

> **覆盖度修复说明（A-8 / X-16）**：
> - A-8：`AdminLoginResponse.admin` 字段类型已从字符串引用 `"AdminBrief"` 修正为直接类型引用 `AdminBrief`。
> - X-16：已解决。架构 §4.1 已对齐，Phase 1 暴露管理 API 为正式设计决策，RBAC 角色守卫（get_current_admin / require_super_admin）替代 Phase 守卫。
