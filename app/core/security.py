"""
app/core/security.py — JWT Token 签发与验证 + RSA 加密工具

架构约束：§5.1 认证流程 / §12 安全
依据：切片 01-auth/backend.md §2
规范：JWT access_token (2h) + refresh_token (7d)，支持 Redis 黑名单撤销
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AppException, ERR_TOKEN_EXPIRED, ERR_UNAUTHORIZED


# 密码哈希工具（bcrypt — 设计要求 §12 安全）
# 注：passlib 1.7.4 与 bcrypt 5.x 不兼容（detect_wrap_bug 触发 ValueError:
# "password cannot be longer than 72 bytes"），因此直接封装 bcrypt 模块，
# 对外保持 pwd_context.hash()/verify() API。
class _PwdContext:
    """密码哈希上下文（bcrypt 直接封装，保持 CryptContext 兼容 API）"""

    @staticmethod
    def hash(password: str) -> str:
        if password is None:
            raise TypeError("password must not be None")
        # bcrypt 限 72 字节，超出部分截断（与 passlib 默认行为一致）
        secret = password.encode("utf-8")[:72]
        return _bcrypt.hashpw(secret, _bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify(password: str, hashed: str) -> bool:
        if not password or not hashed:
            return False
        try:
            return _bcrypt.checkpw(
                password.encode("utf-8")[:72],
                hashed.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False


pwd_context = _PwdContext()


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


# ============================================================================
# RSA 加密工具（密码等敏感数据传输加密）
# ============================================================================

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding


def rsa_encrypt(plaintext: str, public_key_pem: str) -> str:
    """
    RSA 公钥加密（PKCS1 v1.5 padding）。
    返回 base64 编码的密文。
    """
    import base64

    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    ciphertext = public_key.encrypt(
        plaintext.encode(),
        padding.PKCS1v15(),
    )
    return base64.b64encode(ciphertext).decode()


def rsa_decrypt(ciphertext_b64: str, private_key_pem: str) -> str:
    """
    RSA 私钥解密（PKCS1 v1.5 padding）。
    输入 base64 编码的密文，返回明文。
    """
    import base64

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None
    )
    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = private_key.decrypt(
        ciphertext,
        padding.PKCS1v15(),
    )
    return plaintext.decode()


def generate_rsa_keypair() -> tuple[str, str]:
    """
    生成 RSA 密钥对（2048 位）。
    返回 (private_key_pem, public_key_pem)。
    """
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)
