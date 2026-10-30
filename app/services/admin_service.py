"""
app/services/admin_service.py — 管理后台业务逻辑层

依据：API §19 admin 端点（17 个）
      切片 13-infrastructure/admin.md
Admin 独立认证体系：admin_user 表 + Redis session（admin:session:{token}, TTL 30min）
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.core.pagination import paginate, PaginationParams
from app.core.exceptions import AppException, ERR_NOT_FOUND, ERR_FORBIDDEN, ERR_CONFLICT, ERR_ADMIN_INVALID_CREDENTIALS
from app.core.security import pwd_context
from app.models.admin import AdminUser, SystemConfig, AuditLog
from app.models.user import User
from app.models.knowledge_base import KnowledgeCategory, RuleDefinition
# R4-Admin-18: UserBrief → UserManageBrief
from app.schemas.admin import (
    AdminBrief, AdminLoginResponse, UserManageBrief, ConfigBrief,
    AuditLogBrief,
)

logger = logging.getLogger(__name__)

ADMIN_SESSION_TTL = 1800  # 30 分钟
ADMIN_SESSION_PREFIX = "admin:session:"

# R4-Admin-7+8: 配置缓存常量
CONFIG_CACHE_PREFIX = "config:"
CONFIG_CACHE_TTL = 3600  # 1 小时


class AdminService:
    """管理后台服务"""

    # ==================== Admin 认证 ====================

    @staticmethod
    async def login(username: str, password: str) -> AdminLoginResponse:
        """管理员登录"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            admin = result.scalar_one_or_none()

            if not admin or not pwd_context.verify(password, admin.password_hash):
                raise AppException("用户名或密码错误", 401, code=ERR_ADMIN_INVALID_CREDENTIALS)

            if not admin.is_active:
                raise AppException("管理员账号已禁用", 403, code=ERR_FORBIDDEN)

            # 更新最后登录时间
            admin.last_login_at = datetime.now(timezone.utc)
            await db.commit()

        # 创建 Redis session
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
        """管理员登出"""
        redis = await get_redis()
        await redis.delete(f"{ADMIN_SESSION_PREFIX}{token}")

    @staticmethod
    async def get_session(token: str) -> dict | None:
        """获取 admin session 信息"""
        redis = await get_redis()
        data = await redis.get(f"{ADMIN_SESSION_PREFIX}{token}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def refresh_session(token: str) -> None:
        """刷新 session TTL"""
        redis = await get_redis()
        await redis.expire(f"{ADMIN_SESSION_PREFIX}{token}", ADMIN_SESSION_TTL)

    # ==================== 审计日志 ====================

    @staticmethod
    async def _write_audit_log(
        db: AsyncSession,  # 保留参数兼容现有调用，但实际使用独立 session
        admin_id: int | None,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        changes: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """
        写审计日志（内部方法）。使用独立 session，与业务事务隔离。

        R4-Admin-4: 异常吞噬 — 审计日志失败不影响业务事务，仅记录错误日志。
        R5-Admin-6: 使用独立 async_session_factory() 而非调用方 session，
                    确保审计日志独立提交，不随业务事务回滚而丢失。
        """
        try:
            async with async_session_factory() as audit_db:
                log = AuditLog(
                    admin_id=admin_id,
                    user_id=None,  # admin 操作不关联 user 表
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    changes=changes or {},
                    ip_address=ip_address,
                )
                audit_db.add(log)
                await audit_db.commit()
        except Exception as e:
            logging.getLogger(__name__).error(
                "Failed to write audit log: admin_id=%s action=%s target_type=%s error=%s",
                admin_id, action, target_type, e, exc_info=True,
            )
            # 不 re-raise，避免审计日志失败阻塞业务事务

    # ==================== 用户管理 ====================

    @staticmethod
    async def list_users(
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """用户列表查询"""
        async with async_session_factory() as db:
            stmt = select(User)
            if status:
                stmt = stmt.where(User.status == status)
            if q:
                stmt = stmt.where(
                    or_(
                        User.nickname.ilike(f"%{q}%"),
                        User.phone.ilike(f"%{q}%"),
                    )
                )
            stmt = stmt.order_by(desc(User.created_at))

            pagination = PaginationParams(page=page, page_size=min(page_size, 100))
            result = await paginate(db, stmt, pagination)

            return {
                "total": result["total"],
                "page": page,
                "page_size": pagination.page_size,
                "items": [UserManageBrief.model_validate(u) for u in result["items"]],
            }

    # R4-Admin-5: ban_user 返回 {"user_id", "status", "reason"}
    @staticmethod
    async def ban_user(user_id: int, reason: str, admin_id: int, ip_address: str | None = None) -> dict:
        """封禁用户"""
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise AppException("用户不存在", 404, code=ERR_NOT_FOUND)
            if user.status == "banned":
                raise AppException("用户已被封禁", 409, code=ERR_CONFLICT)

            # R4-Admin-6: 审计日志 changes 结构 — 字段级 old/new 对比
            old_status = user.status
            user.status = "banned"
            await db.commit()
            # R12-Admin-6: 审计移到 commit 后（_write_audit_log 独立 session 立即提交，
            # 业务 commit 失败时避免幽灵审计记录）
            await AdminService._write_audit_log(
                db, admin_id, "update", "user", user_id,
                ip_address=ip_address,
                changes={
                    "status": {"old": old_status, "new": "banned"},
                    "ban_reason": {"old": None, "new": reason},
                },
            )
            return {"user_id": user_id, "status": "banned", "reason": reason}

    # R4-Admin-5: unban_user 返回 {"user_id", "status"}
    @staticmethod
    async def unban_user(user_id: int, admin_id: int, ip_address: str | None = None) -> dict:
        """解禁用户"""
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise AppException("用户不存在", 404, code=ERR_NOT_FOUND)
            if user.status != "banned":
                raise AppException("用户未被封禁", 409, code=ERR_CONFLICT)

            old_status = user.status
            user.status = "active"
            await db.commit()
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            await AdminService._write_audit_log(
                db, admin_id, "update", "user", user_id,
                ip_address=ip_address,
                changes={"status": {"old": old_status, "new": "active"}},
            )
            return {"user_id": user_id, "status": "active"}

    # ==================== 系统配置 ====================

    @staticmethod
    async def list_configs() -> list[ConfigBrief]:
        """配置列表"""
        async with async_session_factory() as db:
            # R4-Admin-16: SystemConfig.key → config_key
            result = await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))
            configs = result.scalars().all()
            return [ConfigBrief.model_validate(c) for c in configs]

    # R4-Admin-7+8: get_config Redis 缓存优先；update/delete 失效缓存
    @staticmethod
    async def get_config(key: str) -> ConfigBrief:
        """获取单个配置（Redis 缓存优先，TTL 3600s）"""
        redis = await get_redis()
        cache_key = f"{CONFIG_CACHE_PREFIX}{key}"
        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return ConfigBrief(**data)
        except Exception as e:
            logging.getLogger(__name__).warning("get_config cache read failed: %s", e)

        async with async_session_factory() as db:
            # R4-Admin-16: SystemConfig.key → config_key
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)
            brief = ConfigBrief.model_validate(config)
            # 回填缓存
            try:
                await redis.setex(cache_key, CONFIG_CACHE_TTL, brief.model_dump_json())
            except Exception as e:
                logging.getLogger(__name__).warning("get_config cache write failed: %s", e)
            return brief

    @staticmethod
    async def create_config(key: str, value: str, description: str | None, admin_id: int, ip_address: str | None = None) -> ConfigBrief:
        """创建配置"""
        async with async_session_factory() as db:
            # R4-Admin-16: SystemConfig.key → config_key
            existing = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            if existing.scalar_one_or_none():
                raise AppException("配置已存在", 409, code=ERR_CONFLICT)

            # R4-Admin-16: SystemConfig(key=...) → SystemConfig(config_key=...)
            config = SystemConfig(config_key=key, config_value=value, description=description)
            db.add(config)
            await db.commit()
            await db.refresh(config)
            # R9-Admin-P2-1: 审计日志移到 commit 后，传入 target_id=config.id
            await AdminService._write_audit_log(
                db, admin_id, "create", "config", target_id=config.id,
                ip_address=ip_address,
                changes={
                    "config_key": {"old": None, "new": key},
                    "config_value": {"old": None, "new": value},
                },
            )
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def update_config(key: str, value: str, description: str | None, admin_id: int, ip_address: str | None = None) -> ConfigBrief:
        """更新配置"""
        async with async_session_factory() as db:
            # R4-Admin-16: SystemConfig.key/value → config_key/config_value
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)

            # R5-Admin-5: 捕获更新前的旧值用于审计日志
            old_value = config.config_value
            config.config_value = value
            if description is not None:
                config.description = description
            config_id = config.id
            await db.commit()
            await db.refresh(config)
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            # R12-Admin-5: changes 按 API §19 统一 {old,new} 结构（config_key 裸值移除）
            await AdminService._write_audit_log(
                db, admin_id, "update", "config", target_id=config_id,
                ip_address=ip_address,
                changes={"config_value": {"old": old_value, "new": value}},
            )
            brief = ConfigBrief.model_validate(config)
            # R4-Admin-7+8: 失效缓存
            try:
                redis = await get_redis()
                await redis.delete(f"{CONFIG_CACHE_PREFIX}{key}")
            except Exception as e:
                logging.getLogger(__name__).warning("update_config cache invalidate failed: %s", e)
            return brief

    @staticmethod
    async def delete_config(key: str, admin_id: int, ip_address: str | None = None) -> None:
        """删除配置"""
        async with async_session_factory() as db:
            # R4-Admin-16: SystemConfig.key → config_key
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)

            old_value = config.config_value
            config_id = config.id
            await db.delete(config)
            await db.commit()
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            await AdminService._write_audit_log(
                db, admin_id, "delete", "config", target_id=config_id,
                ip_address=ip_address,
                changes={
                    "config_key": {"old": key, "new": None},
                    "config_value": {"old": old_value, "new": None},
                },
            )
            # R4-Admin-7+8: 失效缓存
            try:
                redis = await get_redis()
                await redis.delete(f"{CONFIG_CACHE_PREFIX}{key}")
            except Exception as e:
                logging.getLogger(__name__).warning("delete_config cache invalidate failed: %s", e)

    # ==================== 审计日志查询 ====================

    # R4-Admin-9+10: 添加 admin_id/start_date/end_date 筛选 + JOIN admin_user 获取 admin_username
    @staticmethod
    async def list_audit_logs(
        action: str | None = None,
        target_type: str | None = None,
        admin_id: int | None = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """审计日志查询（支持按管理员、时间段筛选，JOIN admin_user 获取 admin_username）"""
        async with async_session_factory() as db:
            # LEFT JOIN AdminUser 获取 admin_username
            base = (
                select(AuditLog, AdminUser.username.label("admin_username"))
                .outerjoin(AdminUser, AuditLog.admin_id == AdminUser.id)
            )
            count_stmt = select(func.count()).select_from(AuditLog)
            if action:
                base = base.where(AuditLog.action == action)
                count_stmt = count_stmt.where(AuditLog.action == action)
            if target_type:
                base = base.where(AuditLog.target_type == target_type)
                count_stmt = count_stmt.where(AuditLog.target_type == target_type)
            if admin_id is not None:
                base = base.where(AuditLog.admin_id == admin_id)
                count_stmt = count_stmt.where(AuditLog.admin_id == admin_id)
            if start_date is not None:
                base = base.where(AuditLog.created_at >= start_date)
                count_stmt = count_stmt.where(AuditLog.created_at >= start_date)
            if end_date is not None:
                base = base.where(AuditLog.created_at <= end_date)
                count_stmt = count_stmt.where(AuditLog.created_at <= end_date)

            total = (await db.execute(count_stmt)).scalar() or 0

            effective_page_size = min(page_size, 100)
            offset = (page - 1) * effective_page_size
            stmt = base.order_by(desc(AuditLog.created_at)).offset(offset).limit(effective_page_size)
            rows = (await db.execute(stmt)).all()

            items = []
            for row in rows:
                # row 是 Row 对象，可通过 .AuditLog/.admin_username 或解包访问
                audit_log = row[0]
                admin_username = row[1]
                brief = AuditLogBrief.model_validate(audit_log)
                brief.admin_username = admin_username
                items.append(brief)

            return {
                "total": total,
                "page": page,
                "page_size": effective_page_size,
                "items": items,
            }

    # ==================== 知识库管理 ====================

    @staticmethod
    async def create_category(name: str, code: str, admin_id: int, content: dict | None = None, ip_address: str | None = None) -> dict:
        """创建知识分类"""
        async with async_session_factory() as db:
            # R12-Admin-2: 重复 name/code 返回 409（原直接插入触发 IntegrityError 500）
            dup = await db.scalar(
                select(KnowledgeCategory).where(
                    or_(KnowledgeCategory.name == name, KnowledgeCategory.code == code)
                )
            )
            if dup:
                raise AppException("分类名称或编码已存在", 409, code=ERR_CONFLICT)
            category = KnowledgeCategory(name=name, code=code, content=content or {})
            db.add(category)
            await db.commit()
            await db.refresh(category)
            # R9-Admin-P2-1: 审计日志移到 commit 后，传入 target_id=category.id
            await AdminService._write_audit_log(
                db, admin_id, "create", "knowledge", target_id=category.id,
                ip_address=ip_address,
                changes={
                    "name": {"old": None, "new": name},
                    "code": {"old": None, "new": code},
                },
            )
            return {"id": category.id, "name": category.name, "code": category.code}

    # R4-Admin-11: 仅允许更新 name 和 content（不允许更新 code）
    @staticmethod
    async def update_category(
        category_id: int,
        name: str | None,
        content: dict | None,
        admin_id: int, ip_address: str | None = None,
    ) -> dict:
        """更新知识分类（仅 name/content，code 不可改）"""
        async with async_session_factory() as db:
            result = await db.execute(select(KnowledgeCategory).where(KnowledgeCategory.id == category_id))
            category = result.scalar_one_or_none()
            if not category:
                raise AppException("分类不存在", 404, code=ERR_NOT_FOUND)

            changes: dict = {}
            if name:
                changes["name"] = {"old": category.name, "new": name}
                category.name = name
            if content is not None:
                changes["content"] = {"old": category.content, "new": content}
                category.content = content
            await db.commit()
            await db.refresh(category)
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            await AdminService._write_audit_log(
                db, admin_id, "update", "knowledge", category_id,
                ip_address=ip_address,
                changes=changes,
            )
            return {"id": category.id, "name": category.name, "code": category.code}

    @staticmethod
    async def delete_category(category_id: int, admin_id: int, ip_address: str | None = None) -> None:
        """删除知识分类"""
        async with async_session_factory() as db:
            result = await db.execute(select(KnowledgeCategory).where(KnowledgeCategory.id == category_id))
            category = result.scalar_one_or_none()
            if not category:
                raise AppException("分类不存在", 404, code=ERR_NOT_FOUND)

            old_code = category.code
            await db.delete(category)
            await db.commit()
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            await AdminService._write_audit_log(
                db, admin_id, "delete", "knowledge", category_id,
                ip_address=ip_address,
                changes={"code": {"old": old_code, "new": None}},
            )

    @staticmethod
    async def create_rule(
        rule_id: str, rule_name: str, rule_type: str,
        condition: dict, diagnosis: dict,
        training_methods: list | None = None,
        training_plan_template: str | None = None,
        adjustment_action: str | None = None,
        admin_id: int = 0,
        ip_address: str | None = None,
    ) -> dict:
        """创建知识规则"""
        async with async_session_factory() as db:
            existing = await db.execute(select(RuleDefinition).where(RuleDefinition.rule_id == rule_id))
            if existing.scalar_one_or_none():
                raise AppException("规则已存在", 409, code=ERR_CONFLICT)

            rule = RuleDefinition(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                condition=condition,
                diagnosis=diagnosis,
                # R4-Admin-12: training_methods 类型 list
                training_methods=training_methods or [],
                training_plan_template=training_plan_template,
                # R4-Admin-12: 新增 adjustment_action 字段
                adjustment_action=adjustment_action,
            )
            db.add(rule)
            await db.commit()
            await db.refresh(rule)
            # R9-Admin-P2-1: 审计日志移到 commit 后，传入 target_id=rule.id
            await AdminService._write_audit_log(
                db, admin_id, "create", "knowledge", target_id=rule.id,
                ip_address=ip_address,
                changes={"rule_id": {"old": None, "new": rule_id}},
            )
            # R4-Admin-21: 返回 {"id", "rule_id"}
            return {"id": rule.id, "rule_id": rule.rule_id}

    # R4-Admin-13: toggle_rule 接受 is_active 显式设置而非 toggle
    # R4-Admin-22: 返回 {"id", "is_active"}
    # R12-Admin-4: rule_id 为 int 数据库 ID，按 RuleDefinition.id 查询（对齐 API §19.5.5 与切片设计）
    @staticmethod
    async def toggle_rule(rule_id: int, is_active: bool, admin_id: int, ip_address: str | None = None) -> dict:
        """显式设置规则状态（参数名保留 toggle_rule 兼容）

        rule_id 为 RuleDefinition.id（int 数据库 ID），按主键查询。
        """

        async with async_session_factory() as db:
            result = await db.execute(select(RuleDefinition).where(RuleDefinition.id == rule_id))
            rule = result.scalar_one_or_none()
            if not rule:
                raise AppException("规则不存在", 404, code=ERR_NOT_FOUND)

            old_active = rule.is_active
            rule.is_active = is_active
            await db.commit()
            await db.refresh(rule)
            # R12-Admin-6: 审计移到 commit 后（避免幽灵审计）
            # R12-Admin-5: changes 按 API §19 统一 {is_active:{old,new}}（rule_id 裸值移除）
            await AdminService._write_audit_log(
                db, admin_id, "update", "knowledge", target_id=rule.id,
                ip_address=ip_address,
                changes={"is_active": {"old": old_active, "new": is_active}},
            )
            # R4-Admin-22: 返回 {"id", "is_active"}
            return {"id": rule.id, "is_active": rule.is_active}

    # ==================== 模型版本 ====================

    @staticmethod
    async def activate_model_version(version_id: str, admin_id: int, ip_address: str | None = None) -> dict:
        """激活模型版本"""
        # S6 阶段仅记录审计日志，实际模型管理在 S7+
        async with async_session_factory() as db:
            old_status = None
            await AdminService._write_audit_log(
                db, admin_id, "update", "model",
                ip_address=ip_address,
                changes={"status": {"old": old_status, "new": "active"}},
            )
            await db.commit()
        return {"version_id": version_id, "status": "activated"}
