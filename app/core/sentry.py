"""
app/core/sentry.py — Sentry 错误监控配置

架构约束：§12.8 可观测性 / 切片 13-infrastructure/sentry.md
功能：Sentry SDK 初始化 + 错误捕获
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_sentry_initialized = False


def init_sentry() -> None:
    """初始化 Sentry SDK（生产环境）"""
    global _sentry_initialized
    if _sentry_initialized:
        return

    sentry_dsn = getattr(settings, "SENTRY_DSN", None)
    if not sentry_dsn:
        logger.info("Sentry DSN not configured, skipping initialization")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=settings.ENV,
            traces_sample_rate=0.1 if not settings.is_production else 0.2,
            integrations=[
                FastApiIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
                SqlalchemyIntegration(),
            ],
            ignore_errors=[
                "app.core.exceptions.AppException",
            ],
        )
        _sentry_initialized = True
        logger.info("Sentry initialized successfully (env=%s)", settings.ENV)
    except ImportError:
        logger.warning("sentry-sdk not installed, skipping Sentry initialization")
    except Exception as e:
        logger.warning("Sentry initialization failed: %s", e)


def capture_exception(exc: Exception, **kwargs) -> None:
    """捕获异常到 Sentry"""
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc, **kwargs)
    except ImportError:
        pass
    except Exception:
        pass


def capture_message(msg: str, level: str = "info") -> None:
    """发送消息到 Sentry"""
    try:
        import sentry_sdk
        sentry_sdk.capture_message(msg, level=level)
    except ImportError:
        pass
    except Exception:
        pass
