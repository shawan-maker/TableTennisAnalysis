"""
app/core/limiter.py — 全局 API 限流配置

架构约束：§5.7 端点 / §12 安全
依据：切片总览 §3.5 全局 API 限流配置 / API §1.5 限流配置
规范：基于 slowapi + Redis 后端
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

# 创建限流器实例 — Redis 后端
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url_computed,
    default_limits=["100/minute"],
)

# 导出异常处理器和异常类
rate_limit_exceeded_handler = _rate_limit_exceeded_handler


# 限流规则常量 — 依据 API §1.5
class RateLimits:
    """限流规则常量"""

    # 全局默认
    DEFAULT = "100/minute"

    # 认证相关
    WECHAT_LOGIN = "10/minute"
    PHONE_LOGIN = "5/minute"
    SEND_SMS = "1/minute"
    H5_EXCHANGE = "10/minute"
    CONSENT = "10/minute"
    ADMIN_LOGIN = "5/minute"

    # 业务相关
    AI_ANALYSIS = "10/hour"
    SHARE = "5/day"
    USER_EXPORT = "1/month"
