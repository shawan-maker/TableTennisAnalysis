# 结构化日志配置 — logging

> **模块名称**：`infrastructure / logging`
> **定位**：全局结构化日志配置，基于 `structlog` 输出 JSON 格式日志，统一所有 Service 层关键应用日志（区别于 admin 模块的审计日志 audit_log，应用日志关注运行时行为，审计日志关注管理员操作合规）
> **依据**：MO-1 / INF-6 — 架构 §10 定义使用 structlog，切片 Service 层缺少日志调用

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 结构化输出 | JSON 格式日志，含 timestamp/level/event/module/user_id/request_id 等字段 |
| 请求追踪 | 每个请求分配 `request_id`，贯穿 Service → Celery → WebSocket 全链路 |
| 敏感信息脱敏 | 手机号/openid/token 不打印完整值，仅保留前 4 后 4 |
| 性能安全 | 日志写入异步化，不阻塞请求；DEBUG 级别生产环境关闭 |

---

## 2. 完整实现

```python
# app/core/logging.py
"""结构化日志配置 — 基于 structlog，输出 JSON 格式。

环境变量：
  LOG_LEVEL: DEBUG / INFO / WARNING / ERROR (默认 INFO)
  LOG_FORMAT: json / console (开发环境默认 console，生产默认 json)
"""

import logging
import sys
import structlog
from structlog.types import EventDict, Processor


def _redact_sensitive(_, __, event_dict: EventDict) -> EventDict:
    """脱敏处理器：手机号/token/openid 仅保留前 4 后 4。"""
    sensitive_keys = {"phone", "token", "access_token", "refresh_token",
                      "openid", "session_key", "password", "api_key"}
    for key in list(event_dict.keys()):
        if key in sensitive_keys and isinstance(event_dict[key], str):
            val = event_dict[key]
            if len(val) > 8:
                event_dict[key] = f"{val[:4]}***{val[-4:]}"
    return event_dict


def _add_request_id(_, __, event_dict: EventDict) -> EventDict:
    """注入 request_id（由中间件设置到 contextvar）。"""
    from app.core.context import request_id_var
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(log_level: str = "INFO", log_format: str = "json"):
    """初始化 structlog 配置，在应用启动时调用。

    Args:
        log_level: 日志级别
        log_format: json (生产) 或 console (开发，彩色输出)
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_id,
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准库 logging 兜底（uvicorn / sqlalchemy 等第三方日志）
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(message)s",
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """获取结构化 logger 实例。

    Usage:
        logger = get_logger(__name__)
        logger.info("task_created", user_id=123, task_id=456)
    """
    return structlog.stdlib.get_logger(name)
```

```python
# app/core/context.py
"""请求上下文变量 — request_id 贯穿全链路。"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
```

```python
# app/core/middleware.py (摘录)
"""FastAPI 中间件 — 注入 request_id。"""

import uuid
from app.core.context import request_id_var
from app.core.logging import get_logger

logger = get_logger(__name__)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    request_id_var.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
```

---

## 3. Celery 任务日志关联

```python
# app/ai_pipeline/tasks.py (摘录)
"""Celery 任务通过 contextvar 传递 request_id，保证异步链路日志可追溯。"""

from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, name="ai_pipeline.analyze_video")
def analyze_video_task(self, task_id: int, user_id: int, request_id: str = None):
    """分析任务 — 从 API 传入 request_id，贯穿 10 步流水线。"""
    if request_id:
        request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(task_id=task_id, user_id=user_id)

    logger.info("pipeline_started", task_id=task_id, step=1, total=10)

    try:
        # ... Step 1-10 ...
        logger.info("pipeline_completed", task_id=task_id, duration_sec=elapsed)
    except Exception as e:
        logger.error("pipeline_failed", task_id=task_id, error=str(e), exc_info=True)
        raise
```

---

## 4. Service 层关键应用日志规范

| 场景 | 级别 | 事件名 | 必填字段 |
|------|------|--------|---------|
| 用户登录成功 | INFO | `auth.login_success` | user_id, login_method |
| 登录失败 | WARNING | `auth.login_failed` | phone, reason |
| 视频分析任务创建 | INFO | `video.task_created` | user_id, task_id, duration_sec |
| 分析完成 | INFO | `video.analysis_completed` | task_id, report_id, duration_sec |
| 分析失败 | ERROR | `video.analysis_failed` | task_id, error |
| 支付订单创建 | INFO | `payment.order_created` | user_id, order_no, amount_cents |
| 支付回调成功 | INFO | `payment.callback_success` | order_no, transaction_id |
| 支付回调失败 | ERROR | `payment.callback_failed` | order_no, error |
| 会员到期降级 | WARNING | `membership.downgraded` | user_id, old_tier, new_tier |
| 比赛结束 | INFO | `scoring.match_finished` | match_id, user_id, result |
| 5xx 异常 | ERROR | `system.unhandled_error` | request_id, path, error |

---

## 5. 环境配置

```ini
# .env.example (摘录)

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=json   # 开发环境设为 console 获得彩色输出
```

> **Anti-hallucination 约束**：
> 1. 所有 Service 层关键操作必须通过 `get_logger(__name__)` 记录结构化日志
> 2. 日志字段使用 snake_case，不得硬编码 JSON 字符串
> 3. 敏感信息（手机号/token/openid）必须经过 `_redact_sensitive` 处理器脱敏
> 4. Celery 任务必须从调用方接收 `request_id` 参数，保证链路连续
