"""
app/core/logging.py — structlog 配置

架构约束：§12.8 可观测性 / 切片 13-infrastructure/logging.md
功能：结构化日志，JSON 格式（生产）或 console 格式（开发）
      + 敏感字段脱敏（phone/openid/token）+ request_id 自动注入
"""

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import settings
from app.core.context import request_id_var

# 敏感字段名匹配（用于 dict key 脱敏）
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(phone|mobile|openid|token|access_token|refresh_token|password|secret|api_key)",
    re.IGNORECASE,
)


def _redact_value(value: Any) -> Any:
    """对敏感字符串值脱敏：保留前 4 后 4，中间用 **** 替换。

    非字符串值（数字/bool/None）原样返回；
    长度 <= 8 的字符串全部脱敏为 ****（避免泄露过短的可枚举值）。
    """
    if not isinstance(value, str):
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict,
) -> dict:
    """structlog processor — 递归脱敏事件字典中的敏感字段。

    匹配 key 名包含 phone/openid/token/password/secret/api_key 的字段，
    对其值调用 _redact_value 脱敏。嵌套 dict / list 递归处理。
    监控不应影响业务：任何异常均吞掉并返回原 event_dict。
    """
    try:
        _walk_and_redact(event_dict)
    except Exception:
        # 监控脱敏不得影响日志输出
        pass
    return event_dict


def _walk_and_redact(obj: Any) -> None:
    """递归遍历 dict/list，对敏感 key 的值就地脱敏。"""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if isinstance(k, str) and _SENSITIVE_KEY_PATTERNS.search(k):
                v = obj[k]
                if isinstance(v, (str,)):
                    obj[k] = _redact_value(v)
                elif isinstance(v, (dict, list)):
                    _walk_and_redact(v)
                # 数字/bool/None 不脱敏
            else:
                v = obj[k]
                if isinstance(v, (dict, list)):
                    _walk_and_redact(v)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _walk_and_redact(item)


def _add_request_id(
    _logger: Any, _method_name: str, event_dict: dict,
) -> dict:
    """structlog processor — 从 request_id_var 注入 request_id 到每条日志。

    便于通过 request_id 串联单次请求的全部日志，与响应头 X-Request-ID 对齐。
    """
    try:
        rid = request_id_var.get()
        if rid:
            event_dict["request_id"] = rid
    except Exception:
        pass
    return event_dict


def configure_logging() -> None:
    """配置 structlog 结构化日志"""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 标准 logging 配置
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )

    # structlog 配置
    processors = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        _redact_sensitive,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取 structlog logger"""
    return structlog.get_logger(name)
