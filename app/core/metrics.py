"""
app/core/metrics.py — Prometheus 指标采集

架构约束：§12.8 可观测性 / 切片 13-infrastructure/metrics.md
功能：Prometheus 自定义指标定义 + /metrics 端点
"""

import logging
import time
from functools import wraps

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = logging.getLogger(__name__)

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


def metrics_endpoint():
    """Prometheus /metrics 端点"""
    from fastapi import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


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
