# Prometheus 指标采集 — metrics

> **模块名称**：`infrastructure / metrics`
> **定位**：全局 Prometheus 指标采集，覆盖 API 性能、AI 流水线、支付、业务计数等关键路径
> **依据**：MO-3 / INF-11 — 架构定义 Prometheus 指标采集，切片无指标定义

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 自动采集 | HTTP 请求延迟/状态码通过 `prometheus-fastapi-instrumentator` 自动采集 |
| 业务指标 | AI 分析耗时、支付金额、会员转化率等自定义 Counter/Histogram |
| 暴露端点 | `/metrics` 端点供 Prometheus scrape（仅内网访问） |
| 低开销 | 指标采集使用异步更新，不影响请求延迟 |

---

## 2. 完整实现

```python
# app/core/metrics.py
"""Prometheus 指标定义与配置。

依赖：
  prometheus-fastapi-instrumentator
  prometheus-client
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

# ---------------------------------------------------------------------------
# 1. 自动采集的 HTTP 指标（Instrumentator 自动注册）
#    - http_request_duration_seconds (Histogram)
#    - http_requests_total (Counter)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 2. AI 流水线业务指标
# ---------------------------------------------------------------------------

ai_analysis_total = Counter(
    "ai_analysis_total",
    "AI 视频分析任务总数",
    ["status"],  # status: queued / processing / completed / failed
)

ai_analysis_duration_seconds = Histogram(
    "ai_analysis_duration_seconds",
    "AI 单次分析耗时（秒）",
    buckets=[30, 60, 120, 300, 600, 1200],
)

ai_pipeline_step_duration_seconds = Histogram(
    "ai_pipeline_step_duration_seconds",
    "AI 流水线单步耗时",
    ["step_name"],  # step_name: preprocess / ball_detect / ball_track / pose / action / landing / aggregate / report
    buckets=[5, 10, 30, 60, 120, 300],
)

gpu_inference_queue_depth = Gauge(
    "gpu_inference_queue_depth",
    "GPU 推理队列积压深度",
)

gpu_memory_usage_bytes = Gauge(
    "gpu_memory_usage_bytes",
    "GPU 显存使用量（字节）",
    ["instance"],
)

# ---------------------------------------------------------------------------
# 3. 支付业务指标
# ---------------------------------------------------------------------------

payment_order_total = Counter(
    "payment_order_total",
    "支付订单创建总数",
    ["product_type"],  # product_type: membership / analysis_pack
)

payment_amount_total = Counter(
    "payment_amount_cents_total",
    "支付金额累计（分）",
    ["product_type", "tier"],  # tier: member / pro / coach
)

payment_callback_duration_seconds = Histogram(
    "payment_callback_duration_seconds",
    "支付回调处理耗时",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

# ---------------------------------------------------------------------------
# 4. 会员业务指标
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
# 5. WebSocket 连接指标
# ---------------------------------------------------------------------------

ws_active_connections = Gauge(
    "ws_active_connections",
    "WebSocket 活跃连接数",
)

# ---------------------------------------------------------------------------
# 6. 应用信息
# ---------------------------------------------------------------------------

app_info = Info(
    "app",
    "应用版本信息",
)


def configure_metrics(app):
    """配置 Prometheus 指标采集，在应用启动时调用。

    Args:
        app: FastAPI 应用实例
    """
    Instrumentator(
        should_group_unmatched_paths=True,
        excluded_paths=["/metrics", "/docs", "/redoc", "/openapi.json"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        tags=["monitoring"],
    )

    app_info.info({
        "version": "1.0.0",
        "env": "dev",
    })
```

```python
# app/main.py (摘录)
from app.core.metrics import configure_metrics

configure_metrics(app)
```

---

## 3. 业务埋点示例

### AI 流水线埋点

```python
# app/ai_pipeline/tasks.py (摘录)
from app.core.metrics import (
    ai_analysis_total, ai_analysis_duration_seconds,
    ai_pipeline_step_duration_seconds, gpu_inference_queue_depth,
)
import time

@celery_app.task(bind=True, name="ai_pipeline.analyze_video")
def analyze_video_task(self, task_id: int, user_id: int):
    start_time = time.time()
    ai_analysis_total.labels(status="processing").inc()

    try:
        for step_name in ["preprocess", "ball_detect", "ball_track", "pose",
                          "action", "landing", "aggregate", "report"]:
            step_start = time.time()
            # ... 执行步骤 ...
            ai_pipeline_step_duration_seconds.labels(step_name=step_name).observe(
                time.time() - step_start
            )

        ai_analysis_total.labels(status="completed").inc()
    except Exception:
        ai_analysis_total.labels(status="failed").inc()
        raise
    finally:
        ai_analysis_duration_seconds.observe(time.time() - start_time)
```

### 支付回调埋点

```python
# 11-payment/backend.md Service 层 (摘录)
from app.core.metrics import payment_order_total, payment_amount_total, payment_callback_duration_seconds

async def handle_notify(self, raw_body: bytes, signature: str):
    start = time.time()
    try:
        # ... 验签 + 解密 + 业务处理 ...
        payment_order_total.labels(product_type=order.product_type).inc()
        payment_amount_total.labels(
            product_type=order.product_type, tier=order.tier
        ).inc(order.amount_cents)
    finally:
        payment_callback_duration_seconds.observe(time.time() - start)
```

### WebSocket 连接埋点

```python
# app/api/v1/ws.py (摘录)
from app.core.metrics import ws_active_connections

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    ws_active_connections.inc()
    try:
        # ... 连接处理 ...
    finally:
        ws_active_connections.dec()
```

---

## 4. 指标与告警映射

| Prometheus 指标 | 告警条件 | 对应架构 §13.1 告警 |
|----------------|---------|-------------------|
| `http_request_duration_seconds` P95 | > 0.5 | API P95 延迟 > 500ms ⚠️ |
| `http_request_duration_seconds` P99 | > 2.0 | API P99 延迟 > 2s 🔴 |
| `ai_analysis_duration_seconds` | > 600 | 单任务分析耗时 > 10min ⚠️ |
| `gpu_inference_queue_depth` | > 10 | 队列积压深度 > 10 ⚠️ |
| `ai_analysis_total{status="failed"}` rate | > 5% | 分析失败率 > 5% 🔴 |
| `ws_active_connections` | > 5000 | WebSocket 活跃连接 > 5000 ⚠️ |

---

## 5. 安全约束

> **Anti-hallucination 约束**：
> 1. `/metrics` 端点不暴露到公网，仅允许内网 Prometheus scrape
> 2. 业务指标 Label 值使用枚举常量（如 `status="completed"`），禁止使用自由文本
> 3. Counter 只增不减；Gauge 可增可减；Histogram 桶边界需覆盖业务实际分布
> 4. 指标采集不得在 try-except 的 except 块中抛出异常（监控不应影响业务）
