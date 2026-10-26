"""
app/core/metrics.py — Prometheus 指标采集

架构约束：§12.8 可观测性 / 切片 13-infrastructure/metrics.md
功能：Prometheus 自定义指标定义 + /metrics 端点
      + configure_metrics(app) 配置采集并暴露端点

防御性设计：prometheus_client / prometheus_fastapi_instrumentator 为可选依赖，
未安装时退化为 no-op，保证应用可正常启动（指标采集不得阻断业务）。
"""

import logging
import time
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# 防御性导入：prometheus_client 为可选依赖，缺失时退化为 no-op 指标
# ============================================================================
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:  # prometheus_client 未安装
    _PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

    class _NoopMetric:
        """prometheus_client 缺失时的 no-op 指标占位。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> "_NoopMetric":
            return self

        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, *args: Any, **kwargs: Any) -> None:
            pass

        def info(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dec(self, *args: Any, **kwargs: Any) -> None:
            pass

    Counter = Gauge = Histogram = Info = _NoopMetric  # type: ignore[assignment,misc]

    def generate_latest() -> bytes:  # type: ignore[no-redef]
        return b"# prometheus_client not installed\n"

# ============================================================================
# 指标定义
# ============================================================================

# HTTP 请求计数
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

# HTTP 请求延迟
http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# 活跃用户数
active_users = Gauge(
    "active_users_total",
    "Number of active users",
)

# 视频分析任务计数
video_analysis_tasks_total = Counter(
    "video_analysis_tasks_total",
    "Total video analysis tasks",
    ["status"],
)

# AI 推理延迟
ai_inference_duration = Histogram(
    "ai_inference_duration_seconds",
    "AI inference duration in seconds",
    buckets=[0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# Celery 任务计数
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],
)

# Redis 连接池使用
redis_connections = Gauge(
    "redis_connections_active",
    "Active Redis connections",
)

# ---------------------------------------------------------------------------
# 支付业务指标（设计 metrics.md §3）— R4-Infra-4 补全
# ---------------------------------------------------------------------------

payment_order_total = Counter(
    "payment_order_total",
    "支付订单创建总数",
    ["product_type"],  # product_type: membership / analysis_pack
)

payment_amount_total = Counter(
    "payment_amount_cents_total",
    "支付金额累计（分）",
    ["product_type", "tier"],
)

payment_callback_duration = Histogram(
    "payment_callback_duration_seconds",
    "支付回调处理耗时",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

# ---------------------------------------------------------------------------
# 会员业务指标（设计 metrics.md §4）— R4-Infra-4 补全
# ---------------------------------------------------------------------------

membership_active_count = Gauge(
    "membership_active_count",
    "当前活跃会员数",
    ["tier"],  # tier: member / pro / coach
)

membership_downgrade_total = Counter(
    "membership_downgrade_total",
    "会员降级总次数",
    ["from_tier", "to_tier"],
)

# ---------------------------------------------------------------------------
# WebSocket 连接指标（设计 metrics.md §5）— R4-Infra-4 补全
# ---------------------------------------------------------------------------

ws_active_connections = Gauge(
    "ws_active_connections",
    "WebSocket 活跃连接数",
)

# ---------------------------------------------------------------------------
# 应用信息（设计 metrics.md §6）— R4-Infra-4 补全
# ---------------------------------------------------------------------------

app_info = Info(
    "app",
    "应用版本信息",
)


def metrics_endpoint():
    """Prometheus /metrics 端点"""
    from fastapi import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def configure_metrics(app) -> None:
    """配置 Prometheus 指标采集，在应用启动时调用。

    优先使用 prometheus_fastapi_instrumentator 自动采集 HTTP 指标并暴露 /metrics；
    若未安装则跳过自动采集（/metrics 端点仍由 main.py 手动注册的
    metrics_endpoint 提供，仅返回自定义业务指标）。

    监控不得阻断业务：任何异常均记录日志后吞掉。
    """
    # 设置应用版本信息
    try:
        from app.core.config import settings
        app_info.info({
            "version": "0.6.0",
            "env": settings.ENV,
            "app": settings.APP_NAME,
        })
    except Exception as e:
        logger.warning("configure_metrics app_info failed: %s", e)

    # 尝试 Instrumentator 自动采集 HTTP 指标 + 暴露 /metrics
    if not _PROMETHEUS_AVAILABLE:
        logger.info(
            "prometheus_client not installed, metrics collection disabled"
        )
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            should_group_unmatched_paths=True,
            excluded_paths=["/metrics", "/docs", "/redoc", "/openapi.json"],
        ).instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            tags=["monitoring"],
        )
        logger.info("Prometheus metrics configured via Instrumentator")
    except ImportError:
        # instrumentator 未安装：/metrics 仍由 main.py 手动注册的端点提供
        logger.info(
            "prometheus_fastapi_instrumentator not installed, "
            "falling back to manual /metrics endpoint"
        )
    except Exception as e:
        logger.warning("configure_metrics Instrumentator failed: %s", e)


def track_request_duration(method: str, endpoint: str):
    """装饰器：记录请求延迟"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                http_requests_total.labels(
                    method=method, endpoint=endpoint, status="200"
                ).inc()
                return result
            except Exception as e:
                status = "500"
                if hasattr(e, "status_code"):
                    status = str(e.status_code)
                http_requests_total.labels(
                    method=method, endpoint=endpoint, status=status
                ).inc()
                raise
            finally:
                duration = time.time() - start
                http_request_duration.labels(
                    method=method, endpoint=endpoint
                ).observe(duration)

        return wrapper
    return decorator
