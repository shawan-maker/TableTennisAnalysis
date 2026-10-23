"""
app/core/logging.py — structlog 配置

架构约束：§12.8 可观测性 / 切片 13-infrastructure/logging.md
功能：结构化日志，JSON 格式（生产）或 console 格式（开发）
"""

import logging
import sys

import structlog

from app.core.config import settings


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
