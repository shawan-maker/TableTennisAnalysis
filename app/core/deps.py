"""
app/core/deps.py — FastAPI 依赖注入

架构约束：§5.1 认证流程 / §12 安全 / 切片 01-auth/backend.md §6.1
功能：get_db / get_redis / get_current_user / get_admin_user
"""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.core.exceptions import AppException, ERR_FORBIDDEN, ERR_UNAUTHORIZED

import redis.asyncio as aioredis

# Bearer Token 认证方案
# auto_error=False 手动处理缺失 token，返回 401 而非 FastAPI 默认的 403
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    全局认证依赖 — 解码 JWT → 查询 User → 状态检查 → 返回 User。

    使用方式：
        @router.get("/profile")
        async def get_profile(user: User = Depends(get_current_user)):
            ...

    覆盖范围：共 33 处 Depends(get_current_user) 自动生效。
    例外：auth 的 wechat-login 和 phone-login 不经过此依赖。
    """
    from app.models.user import User

    if credentials is None:
        raise AppException("请先登录", 401, code=ERR_UNAUTHORIZED)

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = int(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise AppException("用户不存在", 401, code=ERR_UNAUTHORIZED)

    # 用户状态检查（PIPL 合规：deleted/banned 状态拒绝业务操作）
    # pending_deletion 允许通过，以便用户撤销注销（72h 冷静期）
    if user.status == "deleted":
        raise AppException("用户不存在", 401, code=ERR_UNAUTHORIZED)
    if user.status == "banned":
        raise AppException("您的账号已被封禁", 403, code=ERR_FORBIDDEN)

    # 检查 JWT 黑名单（Redis）
    redis_client = await get_redis()
    jti = payload.get("jti")
    if jti:
        blacklisted = await redis_client.get(f"jwt:blacklist:{jti}")
        if blacklisted:
            raise AppException("登录已过期，请重新登录", 401, code=ERR_UNAUTHORIZED)

    return user


async def get_current_admin(
    user: "User" = Depends(get_current_user),
):
    """
    管理员权限守卫 — 在 get_current_user 基础上检查管理员身份。

    当前实现：通过 config.ADMIN_USER_IDS 配置管理员用户 ID 列表。
    S6 将替换为 admin_user 表查询。
    """
    from app.core.config import settings

    admin_ids = [int(x.strip()) for x in settings.ADMIN_USER_IDS.split(",") if x.strip()]
    if user.id not in admin_ids:
        raise AppException("管理员权限不足", 403, code=ERR_FORBIDDEN)

    return user


async def get_admin_session(request: Request):
    """
    Admin 独立认证 — 基于 Redis session 的管理员认证。
    与用户 JWT 认证完全独立，使用 admin_user 表 + Redis session（admin:session:{token}）。

    R5-Admin-4: 不使用 HTTPBearer，改为自定义 Header 解析。
    支持 "Admin xxx" 和 "Bearer xxx" 两种 Authorization 前缀。
    """
    from app.services.admin_service import AdminService, ADMIN_SESSION_PREFIX

    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        raise AppException("管理员请先登录", 401, code=ERR_UNAUTHORIZED)

    # 支持 "Admin xxx" 和 "Bearer xxx" 两种前缀
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0] not in ("Admin", "Bearer"):
        raise AppException("管理员请先登录", 401, code=ERR_UNAUTHORIZED)

    token = parts[1]
    session = await AdminService.get_session(token)
    if not session:
        raise AppException("管理员会话已过期，请重新登录", 401, code=ERR_UNAUTHORIZED)

    # 刷新 session TTL
    await AdminService.refresh_session(token)
    return session


async def require_super_admin(
    session: dict = Depends(get_admin_session),
):
    """超级管理员权限守卫"""
    if session.get("role") != "super_admin":
        raise AppException("需要超级管理员权限", 403, code=ERR_FORBIDDEN)
    return session


async def require_content_admin(
    session: dict = Depends(get_admin_session),
):
    """内容管理员权限守卫（super_admin 也通过）"""
    if session.get("role") not in ("super_admin", "content_admin"):
        raise AppException("需要内容管理员权限", 403, code=ERR_FORBIDDEN)
    return session


async def require_model_admin(
    session: dict = Depends(get_admin_session),
):
    """模型管理员权限守卫（super_admin 也通过）"""
    if session.get("role") not in ("super_admin", "model_admin"):
        raise AppException("需要模型管理员权限", 403, code=ERR_FORBIDDEN)
    return session


async def require_membership(
    user: "User" = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会员权限守卫 — 检查用户是否为付费会员（member/pro/analytics_pro）"""
    from app.services.membership_service import MembershipService

    result = await MembershipService.check_membership(db, user.id)
    if not result.is_member:
        raise AppException("此功能需要会员", 403, code=ERR_FORBIDDEN)
    return user


# 便捷导出
__all__ = [
    "get_current_user", "get_current_admin", "get_admin_session",
    "require_super_admin", "require_content_admin", "require_model_admin",
    "require_membership",
    "get_db", "get_redis", "bearer_scheme",
]
