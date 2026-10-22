"""
app/core/security.py — JWT Token 签发与验证 + RSA 加密工具

架构约束：§5.1 认证流程 / §12 安全
依据：切片 01-auth/backend.md §2
规范：JWT access_token (2h) + refresh_token (7d)，支持 Redis 黑名单撤销
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AppException, ERR_TOKEN_EXPIRED, ERR_UNAUTHORIZED


def create_access_token(payload: dict[str, Any]) -> str:
    """
    签发 access_token（2 小时有效期）。

    payload 中应包含：
        - sub: 用户 ID（字符串）
        - jti: 唯一标识（UUID）
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = {
        **payload,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(payload: dict[str, Any]) -> str:
    """
    签发 refresh_token（7 天有效期）。

    payload 中应包含：
        - sub: 用户 ID（字符串）
        - jti: 唯一标识（UUID）
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode = {
        **payload,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(
        to_encode, settings.JWT_REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """
    解码 JWT Token，返回 payload。

    返回 None 表示 Token 无效或已过期。
    注意：此函数不检查 Redis 黑名单，由调用方在需要时检查。
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict[str, Any]]:
    """解码 refresh_token，返回 payload。"""
    try:
        return jwt.decode(
            token, settings.JWT_REFRESH_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码 access_token 并验证类型。

    抛出 AppException(401) 如果 Token 无效或类型不正确。
    """
    payload = decode_token(token)
    if payload is None:
        raise AppException("请先登录", 401, code=ERR_UNAUTHORIZED)

    if payload.get("type") != "access":
        raise AppException("Token 类型错误", 401, code=ERR_UNAUTHORIZED)

    return payload


def generate_jti() -> str:
    """生成 JWT 唯一标识符"""
    return str(uuid.uuid4())
