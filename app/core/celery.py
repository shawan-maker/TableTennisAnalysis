"""
app/core/celery.py — Celery 应用配置

依据：架构 §5.2 / 切片 13-infrastructure/beat_schedule.py.md
功能：Celery app + beat schedule + autodiscover
"""

import os

from celery import Celery

# R13-Test-N3: Celery worker/beat 进程启用 DB NullPool —— 任务经 _run_async/
# asyncio.run 每次执行使用新 event loop，共享连接池会跨 loop 检出死连接
# （RuntimeError: Event loop is closed）。必须在下方 app.core.* 导入
# （beat_schedule → tasks → services → database 传递导入）之前设置。
# 生产 Web 进程（uvicorn app.main）不导入本模块，保留队列池连接复用。
os.environ.setdefault("DB_NULLPOOL", "1")

from app.core.config import settings

celery_app = Celery(
    "pingpong_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_max_tasks_per_child=100,
    # 测试/开发模式下同步执行
    task_always_eager=getattr(settings, "DEBUG", True),
    task_eager_propagates=True,
)

# 注册 beat schedule
from app.core.beat_schedule import configure_beat  # noqa: E402

configure_beat(celery_app)

# autodiscover — 扫描指定模块中的 @shared_task
celery_app.autodiscover_tasks([
    "app.ai_pipeline",
    "app.tasks",
])

celery_app.conf.beat_schedule_timezone = "Asia/Shanghai"
celery_app.conf.beat_sync_every = 1


def get_celery_app() -> Celery:
    """获取 Celery 应用实例"""
    return celery_app
