# 统一 Celery Beat 定时任务调度 — beat_schedule.py

> **模块名称**：`infrastructure / beat_schedule`
> **定位**：汇总所有垂直切片的定时任务，统一配置 Celery Beat 调度
> **依据**：INF-4 — 消除 6+ 个切片各自定义的 beat_schedule 片段

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 单一配置源 | 所有定时任务在一个文件中集中定义，便于审计与排期 |
| 模块隔离 | 任务由各模块注册（`@celery_app.task`），调度在此统一配置 |
| 可观测 | 每个任务带 `description` 注释，便于运维理解用途 |
| 幂等 | 所有定时任务设计为可重复执行，无副作用 |

---

## 2. 完整实现

> **R13-P3 文档同步**：实际 `app/core/beat_schedule.py` 的调度表在 `configure_beat(celery_app)` 函数体内以字典字面量构建并直接赋值 `celery_app.conf.beat_schedule`（**无模块级 `BEAT_SCHEDULE` 常量**），10 个条目内容与本节一致；`beat_schedule_timezone = "Asia/Shanghai"` 与 `beat_sync_every = 1` 由 `app/core/celery.py` 在 `configure_beat()` 之后设置；`beat_send_events` 实际未配置。各条目 `description` 以实现为准（file-management 描述已按 file_management.md §6.2 契约修正）。

```python
# app/core/beat_schedule.py
"""统一 Celery Beat 定时任务调度配置。

将各垂直切片分散的 beat_schedule 片段汇总至此，单一配置源。
各模块只需注册 task（@celery_app.task），调度入口统一在此声明。

维护规则：
  - 新增定时任务 → 在此文件 BEAT_SCHEDULE 字典中追加条目
  - 调整频率 → 修改对应条目的 schedule 字段
  - 临时禁用 → 注释条目即可，勿删除
"""

from celery.schedules import crontab

# ---------------------------------------------------------------------------
# 统一 Beat 调度表
# ---------------------------------------------------------------------------

BEAT_SCHEDULE: dict = {
    # =======================================================================
    # 1. file_management — 孤儿文件清理（每小时）
    # =======================================================================
    "file-management-orphan-cleanup": {
        "task": "app.tasks.file_management.cleanup_orphan_files",
        "schedule": crontab(minute=0),  # 每小时整点
        "options": {"queue": "infra"},
        "description": "扫描 file_record 中 status=uploading 且创建超 1h 的记录，删除 OSS 对象（忽略不存在）并标记 abandoned（R13-P3：与 file_management.md §6.2 契约及实现一致，非“OSS 无 DB 记录关联文件”）",
    },

    # =======================================================================
    # 2. scoring — 废弃比赛自动结束（每小时）
    # =======================================================================
    "scoring-cleanup-abandoned": {
        "task": "app.tasks.scoring.cleanup_abandoned_matches",
        "schedule": crontab(minute=5),  # 每小时第 5 分钟（错峰）
        "options": {"queue": "default"},
        "description": "扫描 status=abandoned 且 abandoned_at 超过 24h 的比赛：更新为 finished（回填 final_score/is_win）并创建 MatchStatistic 空统计占位（避免详情接口 404）",
    },

    # =======================================================================
    # 3. membership — 会员到期检测（每日 00:30）
    # =======================================================================
    "membership-expiry-check": {
        "task": "app.tasks.membership.check_expiry",
        "schedule": crontab(minute=30, hour=0),  # 每日 00:30
        "options": {"queue": "default"},
        "description": "检测到期/即将到期的会员订阅，触发续费提醒与降级流程",
    },

    # =======================================================================
    # 4. notification — 旧通知清理（每月 1 日）
    # =======================================================================
    "notification-old-cleanup": {
        "task": "app.tasks.notification.cleanup_old_notifications",
        "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 每月 1 日 02:00
        "options": {"queue": "infra"},
        "description": "删除 90 天前已读通知记录，删除 180 天前未读通知（归档阈值）",
    },

    # =======================================================================
    # 5. notification — 训练提醒推送（每日 19:00）
    # =======================================================================
    "notification-training-reminder": {
        "task": "app.tasks.notification.training_reminder",
        "schedule": crontab(hour=19, minute=0),  # 每日 19:00
        "options": {"queue": "default"},
        "description": "扫描 >3 天未训练的用户，发送训练提醒推送（同一用户每周最多 2 次）",
    },

    # =======================================================================
    # 6. ai_inference — GPU 健康检查（每 5 分钟）
    # =======================================================================
    "ai-inference-health-check": {
        "task": "app.tasks.ai_inference_health.check_inference_health",
        "schedule": crontab(minute="*/5"),  # 每 5 分钟
        "options": {"queue": "default"},
        "description": "AI 推理服务健康探测：GET /health → Redis 写入可用标记（ai_inference:available，异常时清除并写告警标记），供 ai_pipeline 降级判断；AI_INFERENCE_MOCK=true 时本地模拟恒可用",
    },

    # =======================================================================
    # 7. gamification — 月度积分重置（每月 1 日 00:00）
    # =======================================================================
    "gamification-monthly-points-reset": {
        "task": "app.tasks.gamification.reset_monthly_points",
        "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 每月 1 日 00:00
        "options": {"queue": "default"},
        "description": "归档上月积分快照，重置当月积分计数器",
    },

    # =======================================================================
    # 8. user — 注销账户物理删除（每小时）
    # =======================================================================
    "user-account-deletion": {
        "task": "app.tasks.user.process_account_deletions",
        "schedule": crontab(minute=15),  # 每小时第 15 分钟（错峰）
        "options": {"queue": "default"},
        "description": "扫描标记为 pending_deletion 且 scheduled_deletion_at 已到期的用户账户，执行物理删除（匿名化个人数据）",
    },

    # =======================================================================
    # 9. audit — 审计日志自动清理（每日 03:00）
    # =======================================================================
    "audit-log-cleanup": {
        "task": "app.tasks.audit.cleanup_old_logs",
        "schedule": crontab(minute=0, hour=3),  # 每日 03:00
        "options": {"queue": "infra"},
        "description": "清理超期审计日志（PIPL 合规保留 3 年/1095 天，超期记录删除）",
    },

    # =======================================================================
    # 10. export — 导出任务记录清理（每日 03:00）
    # =======================================================================
    "export-cleanup-old-tasks": {
        "task": "app.tasks.export.cleanup_old_tasks",
        "schedule": crontab(minute=0, hour=3),  # 每日 03:00
        "options": {"queue": "infra"},
        "description": "删除 90 天前 status in (completed, failed) 的导出任务 DB 记录（download_url 指向的 OSS 临时文件删除在 S6+ OSS 接入时补充）",
    },
}

# > **P3 文档同步（R12 / BeatTasks-1 修复后回写）**：R12 已将原 4 个 TODO 空壳 Beat 任务（孤儿清理/审计清理/导出清理/推理健康探测）补齐为真实实现，
# > 任务模块统一落在 `app/tasks/` 下（file_management.py / audit.py / export.py / ai_inference_health.py 等 10 个任务模块，
# > 由 `app/tasks/__init__.py` 显式导入注册），任务名统一为 `app.tasks.{module}.{func}` 全名前缀，
# > Beat 表条目与 Celery 任务注册表（`celery_app.tasks`）逐一断言一致（tests/integration/test_cascade_chains.py::test_beat_tasks_registered_in_celery）。


# ---------------------------------------------------------------------------
# 注册到 Celery App
# ---------------------------------------------------------------------------

def configure_beat(celery_app):
    """将统一调度表注册到 Celery App。

    在 app/core/celery.py 中调用::

        from app.core.beat_schedule import configure_beat
        configure_beat(celery_app)
    """
    celery_app.conf.beat_schedule = BEAT_SCHEDULE
    # R13-P3：实际 configure_beat 仅赋值调度表；beat_schedule_timezone / beat_sync_every
    # 在 app/core/celery.py 中 configure_beat() 调用之后设置；beat_send_events 未配置
```

---

## 3. 调度总览表

| 任务名 | 所属模块 | 调度周期 | 队列 | 说明 |
|--------|----------|----------|------|------|
| `app.tasks.file_management.cleanup_orphan_files` | file_management | 每小时整点 (`crontab(minute=0)`) | infra | 孤儿文件清理（status=uploading 超 1h → 删 OSS 对象 → abandoned，R13-P3 修正） |
| `app.tasks.scoring.cleanup_abandoned_matches` | scoring | 每小时第 5 分 (`crontab(minute=5)`) | default | 废弃比赛自动结束（finished + MatchStatistic 占位） |
| `app.tasks.membership.check_expiry` | membership | 每日 00:30 (`crontab(minute=30, hour=0)`) | default | 会员到期检测 |
| `app.tasks.notification.cleanup_old_notifications` | notification | 每月 1 日 02:00 (`crontab(minute=0, hour=2, day_of_month=1)`) | infra | 已读 90 天/未读 180 天通知清理 |
| `app.tasks.notification.training_reminder` | notification | 每日 19:00 (`crontab(hour=19, minute=0)`) | default | 训练提醒推送 |
| `app.tasks.ai_inference_health.check_inference_health` | ai_inference_health | 每 5 分钟 (`crontab(minute="*/5")`) | default | AI 推理健康探测（Redis 可用标记） |
| `app.tasks.gamification.reset_monthly_points` | gamification | 每月 1 日 00:00 (`crontab(minute=0, hour=0, day_of_month=1)`) | default | 月度积分重置 |
| `app.tasks.user.process_account_deletions` | user | 每小时第 15 分 (`crontab(minute=15)`) | default | 72h 注销账户删除 |
| `app.tasks.audit.cleanup_old_logs` | audit | 每日 03:00 (`crontab(minute=0, hour=3)`) | infra | 3 年审计日志清理（PIPL） |
| `app.tasks.export.cleanup_old_tasks` | export | 每日 03:00 (`crontab(minute=0, hour=3)`) | infra | 90 天导出任务记录清理 |

> 任务注册方式：`app/tasks/__init__.py` 显式导入全部 10 个任务模块（ai_inference_health / audit / export / file_management / gamification / membership / notification / scoring / training / user），`app/core/celery.py` 通过 `autodiscover_tasks(["app.ai_pipeline", "app.tasks"])` 加载注册；异步业务任务（`training_advice.generate_advice`、`app.ai_pipeline.*`）由各业务模块按需投递。

---

## 4. 接入方式

在 `app/core/celery.py` 中导入并注册：

```python
# app/core/celery.py
from celery import Celery

celery_app = Celery("pingpong_ai")

# 基础配置
celery_app.conf.update(
    broker_url="redis://localhost:6379/1",
    result_backend="redis://localhost:6379/2",
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
)

# 注册统一 Beat 调度
from app.core.beat_schedule import configure_beat
configure_beat(celery_app)

# 自动发现各模块任务
# app.tasks 包在 __init__.py 中显式导入全部 10 个任务模块，确保 @shared_task 全部注册
celery_app.autodiscover_tasks([
    "app.ai_pipeline",
    "app.tasks",
])
```

> **P3 文档同步（R12，替代原 R18-P3-18 说明）**：autodiscover 路径与任务名对应关系按当前实现更新：
> - **注册方式**：`app/core/celery.py` 调用 `autodiscover_tasks(["app.ai_pipeline", "app.tasks"])`；`app/tasks/__init__.py` 显式导入全部 10 个任务模块（含 R12 新建的 `app/tasks/export.py`、`app/tasks/audit.py`、`app/tasks/file_management.py`、`app/tasks/ai_inference_health.py`），确保所有 `@shared_task(name="app.tasks.{module}.{func}")` 任务注册到 Celery 任务表。
> - **任务名规范**：R12 起任务名统一为 `app.tasks.{module}.{func}` 全名（原短名如 `scoring.cleanup_abandoned_matches` 已统一为 `app.tasks.scoring.cleanup_abandoned_matches`），Beat 表条目与注册表一致（`test_beat_tasks_registered_in_celery` 逐一断言，防 `UnknownTaskError`）。
> - **异步业务任务**：`training_advice.generate_advice`（`app/tasks/training.py`）与 `app.ai_pipeline` 流水线任务通过 `app.ai_pipeline` 路径加载，由业务端点按需 `.delay()` 投递，不在 Beat 表中。
>
> **R13-P3 文档同步**：实际 `app/core/celery.py` 的 conf 另含 `task_track_started / task_time_limit=3600 / task_soft_time_limit=3000 / worker_max_tasks_per_child=100 / task_always_eager（取 `settings.DEBUG`，测试与开发环境同步执行）/ task_eager_propagates=True`；`beat_schedule_timezone="Asia/Shanghai"` 与 `beat_sync_every=1` 在 `configure_beat(celery_app)` 之后于 celery.py 模块级设置；`beat_send_events` 未配置（样例中的该行不代表实际）。

---

## 5. 运维注意事项

1. **错峰调度**：多个每小时任务使用不同 minute 偏移（0、5），避免瞬时负载峰值
2. **队列分离**：`infra` 队列跑清理类任务，不挤占 `default` 业务队列
3. **幂等保证**：所有定时任务必须可安全重复执行（如孤儿清理使用 `WHERE` 条件而非全表删）
4. **监控**：Beat 启动后可通过 `celery -A app.core.celery inspect active` 查看任务执行情况
5. **禁用任务**：注释 `BEAT_SCHEDULE` 中对应条目即可，无需修改模块代码
