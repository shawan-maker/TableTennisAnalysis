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
from app.core.exceptions import AppException, ERR_NOT_FOUND, ERR_FORBIDDEN, ERR_CONFLICT
from app.core.security import pwd_context
from app.models.admin import AdminUser, SystemConfig, AuditLog
from app.models.user import User
from app.models.knowledge_base import KnowledgeCategory, RuleDefinition
from app.schemas.admin import (
    AdminBrief, AdminLoginResponse, UserBrief, ConfigBrief,
    AuditLogBrief,
)

logger = logging.getLogger(__name__)

ADMIN_SESSION_TTL = 1800  # 30 分钟
ADMIN_SESSION_PREFIX = "admin:session:"


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
                raise AppException("用户名或密码错误", 401, code="ERR_ADMIN_INVALID_CREDENTIALS")

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
        db: AsyncSession,
        admin_id: int | None,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """写审计日志（内部方法）。admin_id 存入 admin_id 列，变更内容存入 changes JSONB。"""
        log = AuditLog(
            admin_id=admin_id,
            user_id=None,  # admin 操作不关联 user 表
            action=action,
            target_type=target_type,
            target_id=target_id,
            changes=detail or {},
            ip_address=ip_address,
        )
        db.add(log)

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
                "items": [UserBrief.model_validate(u) for u in result["items"]],
            }

    @staticmethod
    async def ban_user(user_id: int, reason: str, admin_id: int) -> None:
        """封禁用户"""
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise AppException("用户不存在", 404, code=ERR_NOT_FOUND)
            if user.status == "banned":
                raise AppException("用户已被封禁", 409, code=ERR_CONFLICT)

            user.status = "banned"
            await AdminService._write_audit_log(
                db, admin_id, "ban_user", "user", user_id, {"reason": reason}
            )
            await db.commit()

    @staticmethod
    async def unban_user(user_id: int, admin_id: int) -> None:
        """解禁用户"""
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise AppException("用户不存在", 404, code=ERR_NOT_FOUND)
            if user.status != "banned":
                raise AppException("用户未被封禁", 409, code=ERR_CONFLICT)

            user.status = "active"
            await AdminService._write_audit_log(
                db, admin_id, "unban_user", "user", user_id
            )
            await db.commit()

    # ==================== 系统配置 ====================

    @staticmethod
    async def list_configs() -> list[ConfigBrief]:
        """配置列表"""
        async with async_session_factory() as db:
            result = await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))
            configs = result.scalars().all()
            return [ConfigBrief.model_validate(c) for c in configs]

    @staticmethod
    async def get_config(key: str) -> ConfigBrief:
        """获取单个配置"""
        async with async_session_factory() as db:
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def create_config(key: str, value: str, description: str | None, admin_id: int) -> ConfigBrief:
        """创建配置"""
        async with async_session_factory() as db:
            existing = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            if existing.scalar_one_or_none():
                raise AppException("配置已存在", 409, code=ERR_CONFLICT)

            config = SystemConfig(config_key=key, value=value, description=description)
            db.add(config)
            await AdminService._write_audit_log(
                db, admin_id, "create_config", "system_config", detail={"key": key}
            )
            await db.commit()
            await db.refresh(config)
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def update_config(key: str, value: str, description: str | None, admin_id: int) -> ConfigBrief:
        """更新配置"""
        async with async_session_factory() as db:
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)

            config.config_value = value
            if description is not None:
                config.description = description
            await AdminService._write_audit_log(
                db, admin_id, "update_config", "system_config", detail={"key": key, "value": value}
            )
            await db.commit()
            await db.refresh(config)
            return ConfigBrief.model_validate(config)

    @staticmethod
    async def delete_config(key: str, admin_id: int) -> None:
        """删除配置"""
        async with async_session_factory() as db:
            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            config = result.scalar_one_or_none()
            if not config:
                raise AppException("配置不存在", 404, code=ERR_NOT_FOUND)

            await db.delete(config)
            await AdminService._write_audit_log(
                db, admin_id, "delete_config", "system_config", detail={"key": key}
            )
            await db.commit()

    # ==================== 审计日志查询 ====================

    @staticmethod
    async def list_audit_logs(
        action: str | None = None,
        target_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """审计日志查询"""
        async with async_session_factory() as db:
            stmt = select(AuditLog)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            if target_type:
                stmt = stmt.where(AuditLog.target_type == target_type)
            stmt = stmt.order_by(desc(AuditLog.created_at))

            pagination = PaginationParams(page=page, page_size=min(page_size, 100))
            result = await paginate(db, stmt, pagination)

            return {
                "total": result["total"],
                "page": page,
                "page_size": pagination.page_size,
                "items": [AuditLogBrief.model_validate(a) for a in result["items"]],
            }

    # ==================== 知识库管理 ====================

    @staticmethod
    async def create_category(name: str, code: str, admin_id: int) -> dict:
        """创建知识分类"""
        async with async_session_factory() as db:
            category = KnowledgeCategory(name=name, code=code, content={})
            db.add(category)
            await AdminService._write_audit_log(
                db, admin_id, "create_category", "knowledge_category", detail={"name": name, "code": code}
            )
            await db.commit()
            await db.refresh(category)
            return {"id": category.id, "name": category.name, "code": category.code}

    @staticmethod
    async def update_category(category_id: int, name: str | None, code: str | None, admin_id: int) -> dict:
        """更新知识分类"""
        async with async_session_factory() as db:
            result = await db.execute(select(KnowledgeCategory).where(KnowledgeCategory.id == category_id))
            category = result.scalar_one_or_none()
            if not category:
                raise AppException("分类不存在", 404, code=ERR_NOT_FOUND)

            if name:
                category.name = name
            if code:
                category.code = code
            await AdminService._write_audit_log(
                db, admin_id, "update_category", "knowledge_category", category_id
            )
            await db.commit()
            await db.refresh(category)
            return {"id": category.id, "name": category.name, "code": category.code}

    @staticmethod
    async def delete_category(category_id: int, admin_id: int) -> None:
        """删除知识分类"""
        async with async_session_factory() as db:
            result = await db.execute(select(KnowledgeCategory).where(KnowledgeCategory.id == category_id))
            category = result.scalar_one_or_none()
            if not category:
                raise AppException("分类不存在", 404, code=ERR_NOT_FOUND)

            await db.delete(category)
            await AdminService._write_audit_log(
                db, admin_id, "delete_category", "knowledge_category", category_id
            )
            await db.commit()

    @staticmethod
    async def create_rule(
        rule_id: str, rule_name: str, rule_type: str,
        condition: dict, diagnosis: dict,
        training_methods: dict | None = None,
        training_plan_template: str | None = None,
        admin_id: int = 0,
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
                training_methods=training_methods or {},
                training_plan_template=training_plan_template,
            )
            db.add(rule)
            await AdminService._write_audit_log(
                db, admin_id, "create_rule", "rule_definition", detail={"rule_id": rule_id}
            )
            await db.commit()
            await db.refresh(rule)
            return {"rule_id": rule.rule_id, "rule_name": rule.rule_name}

    @staticmethod
    async def toggle_rule(rule_id: str, admin_id: int) -> dict:
        """切换知识规则状态"""
        async with async_session_factory() as db:
            result = await db.execute(select(RuleDefinition).where(RuleDefinition.rule_id == rule_id))
            rule = result.scalar_one_or_none()
            if not rule:
                raise AppException("规则不存在", 404, code=ERR_NOT_FOUND)

            rule.is_active = not rule.is_active
            await AdminService._write_audit_log(
                db, admin_id, "toggle_rule", "rule_definition", detail={
                    "rule_id": rule_id, "is_active": rule.is_active
                }
            )
            await db.commit()
            await db.refresh(rule)
            return {"rule_id": rule.rule_id, "is_active": rule.is_active}

    # ==================== 模型版本 ====================

    @staticmethod
    async def activate_model_version(version_id: str, admin_id: int) -> dict:
        """激活模型版本"""
        # S6 阶段仅记录审计日志，实际模型管理在 S7+
        async with async_session_factory() as db:
            await AdminService._write_audit_log(
                db, admin_id, "activate_model_version", "model_version", detail={"version_id": version_id}
            )
            await db.commit()
        return {"version_id": version_id, "status": "activated"}
