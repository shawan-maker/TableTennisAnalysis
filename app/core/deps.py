"""
app/core/deps.py — FastAPI 依赖注入

架构约束：§5.1 认证流程 / §12 安全 / 切片 01-auth/backend.md §6.1
功能：get_db / get_redis / get_current_user / get_admin_user
"""

from fastapi import Depends
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

    # 用户状态检查（PIPL 合规：非 active 状态拒绝业务操作）
    if user.status == "pending_deletion":
        raise AppException("您的账号正在注销中，请先撤销注销", 403, code=ERR_FORBIDDEN)
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


# 便捷导出
__all__ = ["get_current_user", "get_db", "get_redis", "bearer_scheme"]
