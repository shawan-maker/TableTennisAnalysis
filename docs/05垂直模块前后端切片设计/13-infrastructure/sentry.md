# Sentry 错误追踪集成 — sentry

> **模块名称**：`infrastructure / sentry`
> **定位**：全局错误追踪，基于 Sentry SDK 自动捕获未处理异常 + 手动上报关键业务错误
> **依据**：MO-2 / INF-7 — 架构定义 Sentry 用于错误追踪，切片无集成代码

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 自动捕获 | 未处理异常自动上报到 Sentry，含 request_id / user_id 上下文 |
| 业务错误上报 | 支付回调失败、AI 分析失败等关键错误手动 `capture_exception` |
| 敏感信息过滤 | 手机号/openid/token 通过 `before_send` 钩子脱敏后上报 |
| 采样控制 | 生产环境 100% ERROR 采样；WARNING 级别 10% 采样 |
| 环境隔离 | dev/staging/prod 环境隔离，dev 环境不上报 |

---

## 2. 完整实现

```python
# app/core/sentry.py
"""Sentry SDK 初始化与配置。

环境变量：
  SENTRY_DSN: Sentry DSN 地址（可选，未配置则跳过初始化）
  ENVIRONMENT: dev / staging / prod
  SENTRY_TRACES_SAMPLE_RATE: 事务采样率（默认 0.1）
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from fastapi import HTTPException
from app.core.exceptions import AppException


SENSITIVE_KEYS = {"phone", "token", "access_token", "refresh_token",
                  "openid", "session_key", "password", "api_key",
                  "wechat_code", "session_key"}


def _before_send(event, hint):
    """before_send 钩子 — 脱敏敏感信息后上报。"""
    if "request" in event and "data" in event["request"]:
        data = event["request"]["data"]
        if isinstance(data, dict):
            for key in list(data.keys()):
                if key in SENSITIVE_KEYS:
                    data[key] = "***REDACTED***"
    # 脱敏 extra 中的敏感字段
    if "extra" in event:
        for key in list(event["extra"].keys()):
            if key in SENSITIVE_KEYS:
                event["extra"][key] = "***REDACTED***"
    return event


def configure_sentry(sentry_dsn: str | None = None,
                     environment: str = "dev",
                     traces_sample_rate: float = 0.1):
    """初始化 Sentry SDK，在应用启动时调用。

    Args:
        sentry_dsn: Sentry DSN 地址，None 则跳过
        environment: 环境标识
        traces_sample_rate: 性能事务采样率
    """
    if not sentry_dsn:
        # dev 环境或未配置 DSN 时不初始化
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        before_send=_before_send,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            CeleryIntegration(),
            RedisIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        # 过滤框架级噪声错误（HTTPException 为 FastAPI 框架路由错误，非业务异常）
        # R27-P3-backend-1: 移除 AppException — 业务异常应上报到 Sentry 以便监控（105/105 异常均为 AppException，全量过滤会导致 Sentry 无业务异常可追踪）
        # 预期业务错误（404/401/409 等）可在 before_send 钩子按 status_code 精细过滤
        ignore_errors=[
            HTTPException,
        ],
    )


def set_user_context(user_id: int, openid: str | None = None):
    """设置 Sentry 用户上下文（登录后调用）。

    Args:
        user_id: 用户 ID
        openid: 微信 openid（脱敏后上报）
    """
    sentry_sdk.set_user({
        "id": str(user_id),
        # 不上报 openid 完整值
        "openid": f"{openid[:4]}***{openid[-4:]}" if openid else None,
    })


def set_request_context(request_id: str):
    """设置 request_id 到 Sentry tag，与结构化日志关联。"""
    sentry_sdk.set_tag("request_id", request_id)
```

```python
# app/main.py (摘录)
"""应用入口 — 初始化 Sentry。"""

from app.core.sentry import configure_sentry
from app.core.config import settings

configure_sentry(
    sentry_dsn=settings.SENTRY_DSN,
    environment=settings.ENVIRONMENT,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
)
```

---

## 3. 全局异常处理器集成

```python
# app/core/exceptions.py (摘录)
"""AppException 全局处理器 — 集成 Sentry 上报。"""

import sentry_sdk
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """处理业务异常 — 记录结构化日志 + 5xx 上报 Sentry。"""
    logger.warning(
        "app_exception",
        path=request.url.path,
        message=exc.message,
        code=exc.code,
        status_code=exc.status_code,
    )

    # 5xx 错误上报 Sentry（4xx 为业务错误，不上报）
    if exc.status_code >= 500:
        sentry_sdk.capture_exception(exc)

    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.message, "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """处理未捕获异常 — 记录 ERROR 日志 + 上报 Sentry。"""
    logger.error(
        "unhandled_error",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    sentry_sdk.capture_exception(exc)

    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务内部错误", "data": None},
    )
```

---

## 4. 关键业务错误手动上报

| 场景 | 上报方式 | 附加上下文 |
|------|---------|-----------|
| AI 分析流水线失败 | `sentry_sdk.capture_exception(exc)` | task_id, user_id, failed_step |
| 微信支付回调验签失败 | `sentry_sdk.capture_message("wechat_pay_sign_failed", level="error")` | order_no |
| GPU OOM 恢复失败 | `sentry_sdk.capture_exception(exc)` | gpu_memory, model_name |
| Celery 任务重试耗尽 | `sentry_sdk.capture_message("celery_task_exhausted", level="error")` | task_name, retry_count |

```python
# 示例：AI 分析失败上报
try:
    result = await inference_service.call_gpu_api(video_frames)
except Exception as e:
    logger.error("gpu_inference_failed", task_id=task_id, error=str(e))
    sentry_sdk.capture_exception(e)
    raise PipelineError(f"GPU 推理失败: {e}")
```

---

## 5. 环境配置

```ini
# .env.example (摘录)

# Sentry (可选)
SENTRY_DSN=                          # 留空则跳过 Sentry 初始化
ENVIRONMENT=dev                      # dev / staging / prod
SENTRY_TRACES_SAMPLE_RATE=0.1        # 性能事务采样率
```

> **Anti-hallucination 约束**：
> 1. `AppException`（业务异常）不上报 Sentry，仅 5xx 和未捕获异常上报
> 2. `before_send` 钩子必须脱敏所有敏感字段后上报
> 3. dev 环境不初始化 Sentry（`SENTRY_DSN` 为空时自动跳过）
> 4. Sentry `request_id` tag 必须与结构化日志的 `request_id` 一致
