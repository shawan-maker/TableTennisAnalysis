"""
app/core/sentry.py — Sentry 错误监控配置

架构约束：§12.8 可观测性 / 切片 13-infrastructure/sentry.md
功能：Sentry SDK 初始化 + 错误捕获
      + before_send 钩子对 phone/openid/token 脱敏（§12.5 PII 合规）
      + ignore_errors 仅过滤 HTTPException（AppException 是业务异常，仍需上报监控）
"""

import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_sentry_initialized = False

# 敏感字段名匹配（与 logging.py 一致）
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(phone|mobile|openid|token|access_token|refresh_token|password|secret|api_key)",
    re.IGNORECASE,
)


def _redact_value(value: Any) -> Any:
    """对敏感字符串值脱敏：保留前 4 后 4，中间用 **** 替换。"""
    if not isinstance(value, str):
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _scrub_sensitive(obj: Any) -> Any:
    """递归遍历 dict/list，对敏感 key 的值就地脱敏。返回原对象（就地修改）。"""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if isinstance(k, str) and _SENSITIVE_KEY_PATTERNS.search(k):
                v = obj[k]
                if isinstance(v, str):
                    obj[k] = _redact_value(v)
                elif isinstance(v, (dict, list)):
                    _scrub_sensitive(v)
            else:
                v = obj[k]
                if isinstance(v, (dict, list)):
                    _scrub_sensitive(v)
    elif isinstance(obj, list):
        for item in obj:
            _scrub_sensitive(item)
    return obj


def _before_send(event: dict, hint: dict) -> dict | None:
    """Sentry before_send 钩子 — 上报前对 phone/openid/token 等敏感字段脱敏。

    处理 dict 类型的 event data（可能含 phone/openid/token 字段）：
    - event["request"]["data"] / event["request"]["headers"]
    - event["exception"][*]["stacktrace"][*]["vars"]
    - event["extra"]
    - event["breadcrumbs"][*]["data"]

    监控不应影响业务：任何异常均吞掉并原样返回 event。
    """
    try:
        # request body / headers
        request = event.get("request") or {}
        if isinstance(request, dict):
            data = request.get("data")
            if isinstance(data, dict):
                _scrub_sensitive(data)
            headers = request.get("headers")
            if isinstance(headers, dict):
                _scrub_sensitive(headers)

        # exception stacktrace local variables
        exceptions = event.get("exception") or {}
        if isinstance(exceptions, dict):
            for exc in exceptions.get("values", []) or []:
                if not isinstance(exc, dict):
                    continue
                stacktrace = exc.get("stacktrace") or {}
                if not isinstance(stacktrace, dict):
                    continue
                for frame in stacktrace.get("frames", []) or []:
                    if not isinstance(frame, dict):
                        continue
                    vars_ = frame.get("vars")
                    if isinstance(vars_, dict):
                        _scrub_sensitive(vars_)

        # extra context
        extra = event.get("extra")
        if isinstance(extra, dict):
            _scrub_sensitive(extra)

        # breadcrumbs data
        breadcrumbs = event.get("breadcrumbs") or {}
        if isinstance(breadcrumbs, dict):
            for crumb in breadcrumbs.get("values", []) or []:
                if isinstance(crumb, dict):
                    cdata = crumb.get("data")
                    if isinstance(cdata, dict):
                        _scrub_sensitive(cdata)
    except Exception:
        # 监控脱敏不得影响上报
        pass
    return event


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

        # FastAPI HTTPException 用于框架层路由/参数校验错误，
        # 属预期内错误、无需告警；AppException 是业务异常，仍需上报监控以便发现真实故障
        from fastapi import HTTPException

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
            ignore_errors=[HTTPException],
            before_send=_before_send,
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
