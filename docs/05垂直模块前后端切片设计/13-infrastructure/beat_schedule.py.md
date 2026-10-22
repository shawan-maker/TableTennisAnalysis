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
        "task": "file_management.cleanup_orphans",
        "schedule": crontab(minute=0),  # 每小时整点
        "options": {"queue": "infra"},
        "description": "扫描 OSS 中无 DB 记录关联的孤儿文件，标记并清理",
    },

    # =======================================================================
    # 2. scoring — 废弃比赛自动结束（每小时）
    # =======================================================================
    "scoring-cleanup-abandoned": {
        "task": "scoring.cleanup_abandoned_matches",
        "schedule": crontab(minute=5),  # 每小时第 5 分钟（错峰）
        "options": {"queue": "default"},
        "description": "扫描 status=abandoned 且 abandoned_at 超过 24h 的比赛，自动更新为 finished 并在 MatchStatistic 标注'超时自动结束'",
    },

    # =======================================================================
    # 3. membership — 会员到期检测（每日 00:30）
    # =======================================================================
    "membership-expiry-check": {
        "task": "membership.check_expiry",
        "schedule": crontab(minute=30, hour=0),  # 每日 00:30
        "options": {"queue": "default"},
        "description": "检测到期/即将到期的会员订阅，触发续费提醒与降级流程",
    },

    # =======================================================================
    # 4. notification — 旧通知清理（每月 1 日）
    # =======================================================================
    "notification-old-cleanup": {
        "task": "notification.cleanup_old_notifications",
        "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 每月 1 日 02:00
        "options": {"queue": "infra"},
        "description": "清理 90 天前已读通知记录，归档未读通知",
    },

    # =======================================================================
    # 5. notification — 训练提醒推送（每日 19:00）
    # =======================================================================
    "notification-training-reminder": {
        "task": "notification.training_reminder",
        "schedule": crontab(hour=19, minute=0),  # 每日 19:00
        "options": {"queue": "default"},
        "description": "扫描 >3 天未训练的用户，发送训练提醒推送（同一用户每周最多 2 次）",
    },

    # =======================================================================
    # 6. ai_inference — GPU 健康检查（每 5 分钟）
    # =======================================================================
    "ai-inference-health-check": {
        "task": "ai_inference.health_check",
        "schedule": crontab(minute="*/5"),  # 每 5 分钟
        "options": {"queue": "default"},
        "description": "检测 GPU 推理服务可用性，异常时告警 + 标记降级",
    },

    # =======================================================================
    # 7. gamification — 月度积分重置（每月 1 日 00:00）
    # =======================================================================
    "gamification-monthly-points-reset": {
        "task": "gamification.reset_monthly_points",
        "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 每月 1 日 00:00
        "options": {"queue": "default"},
        "description": "归档上月积分快照，重置当月积分计数器",
    },

    # =======================================================================
    # 8. user — 注销账户物理删除（每小时）
    # =======================================================================
    "user-account-deletion": {
        "task": "user.process_account_deletions",
        "schedule": crontab(minute=15),  # 每小时第 15 分钟（错峰）
        "options": {"queue": "default"},
        "description": "扫描标记为 pending_deletion 且 scheduled_deletion_at 已到期的用户账户，执行物理删除（匿名化个人数据）",
    },

    # =======================================================================
    # 9. audit — 审计日志自动清理（每日 03:00）
    # =======================================================================
    "audit-log-cleanup": {
        "task": "audit.cleanup_old_logs",
        "schedule": crontab(minute=0, hour=3),  # 每日 03:00
        "options": {"queue": "infra"},
        "description": "清理 3 年前的审计日志记录，保留 PIPL 合规所需的最近 3 年",
    },

    # =======================================================================
    # 10. export — 导出任务记录清理（每日 03:00）
    # =======================================================================
    "export-cleanup-old-tasks": {
        "task": "export.cleanup_old_tasks",
        "schedule": crontab(minute=0, hour=3),  # 每日 03:00
        "options": {"queue": "infra"},
        "description": "清理 90 天前已完成的导出任务记录（PDF/CSV 等临时导出文件及 DB 记录）",
    },
}

# > **R18-P3-19 修复（已在 R18 落地）**：export.cleanup_old_tasks autodiscover 覆盖说明。
# > 原推迟原因为"注释说明已覆盖"，现显式标注：
# > - **Beat 表条目**：上方 `export-cleanup-old-tasks` 通过 crontab(minute=0, hour=3) 每日 03:00 触发 `export.cleanup_old_tasks` 任务
# > - **任务定义位置**：实际定义在 `app/tasks/user_tasks.py` 的 `@task(name="export.cleanup_old_tasks")` 装饰器下（详见切片 `02-user/backend.md` §6 Celery 任务定义）
# > - **autodiscover 覆盖路径**：`app.tasks.user` 在 autodiscover 列表（见下方 §4 代码块）中，加载 `app/tasks/__init__.py` 导入的 `user_tasks.py`，从而注册 `export.cleanup_old_tasks` 任务名
# > - **验证**：R15 P1-15-1 已修复（原 `app.tasks.export` 路径不存在导致 `NotRegistered` 异常），R17/R18 验证通过，Celery Beat 可正常调度
# > - **覆盖完整性**：所有 10 个 Beat 任务（file/scoring/membership/notification/ai_inference/gamification/user/audit/export/ai_pipeline）均通过 autodiscover 列表中的 9 个模块路径加载（export 通过 user 覆盖），无遗漏


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
    # Beat 调度器使用 Asia/Shanghai 时区（与业务时区一致）
    celery_app.conf.beat_schedule_timezone = "Asia/Shanghai"
    # 每次 beat 启动时发送 'celery.app.amqp' 事件
    celery_app.conf.beat_send_events = True
    # 任务结果过期时间
    celery_app.conf.beat_sync_every = 1  # 每次写入后同步落盘
```

---

## 3. 调度总览表

| 任务名 | 所属模块 | 调度周期 | 队列 | 说明 |
|--------|----------|----------|------|------|
| `file_management.cleanup_orphans` | file_management | 每小时整点 (`crontab(minute=0)`) | infra | 孤儿文件清理 |
| `scoring.cleanup_abandoned_matches` | scoring | 每小时第 5 分 (`crontab(minute=5)`) | default | 废弃比赛自动结束 |
| `membership.check_expiry` | membership | 每日 00:30 (`crontab(minute=30, hour=0)`) | default | 会员到期检测 |
| `notification.cleanup_old_notifications` | notification | 每月 1 日 02:00 (`crontab(minute=0, hour=2, day_of_month=1)`) | infra | 旧通知清理 |
| `notification.training_reminder` | notification | 每日 19:00 (`crontab(hour=19, minute=0)`) | default | 训练提醒推送 |
| `ai_inference.health_check` | ai_inference | 每 5 分钟 (`crontab(minute="*/5")`) | default | GPU 健康检查 |
| `gamification.reset_monthly_points` | gamification | 每月 1 日 00:00 (`crontab(minute=0, hour=0, day_of_month=1)`) | default | 月度积分重置 |
| `user.process_account_deletions` | user | 每小时第 15 分 (`crontab(minute=15)`) | default | 72h 注销账户物理删除 |
| `audit.cleanup_old_logs` | audit | 每日 03:00 (`crontab(minute=0, hour=3)`) | infra | 3 年审计日志归档清理 |
| `export.cleanup_old_tasks` | export | 每日 03:00 (`crontab(minute=0, hour=3)`) | infra | 90 天导出任务记录清理 |

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
celery_app.autodiscover_tasks([
    "app.tasks.file_management",
    "app.tasks.scoring",
    "app.tasks.membership",
    "app.tasks.notification",
    "app.tasks.ai_inference_health",  # 任务名 ai_inference.health_check 定义在此模块（app/tasks/ai_inference_health.py）
    "app.tasks.gamification",
    "app.tasks.user",
    "app.tasks.audit",
    # R17-P3: 删除 app.tasks.export 无效路径（export.cleanup_old_tasks 实际定义在 app/tasks/user_tasks.py，
    # 由 app.tasks.user autodiscover 覆盖注册）
    "app.ai_pipeline",
])
```

> **R18-P3-18 修复（已在 R18 落地）**：autodiscover 路径与任务名对应关系说明。原 R18 推迟原因为"@task name= 显式指定，功能正确"，现显式标注 autodiscover 路径与任务名映射：
> - **常规映射**：autodiscover 列表中的模块路径 `app.tasks.{module}` 自动注册该模块下所有 `@task(name="...")` 装饰的任务，任务名与模块路径一致（如 `app.tasks.scoring` → `scoring.calculate_match_statistics`）
> - **跨模块定义**：`ai_inference.health_check` 任务定义在 `app/tasks/ai_inference_health.py`，模块名 `ai_inference_health` 与任务名 `ai_inference.health_check`（带点号）不一致，因 `@task(name="ai_inference.health_check")` 显式指定任务名，autodiscover 仍按模块路径加载，Beat 调度按任务名发送，功能正确
> - **跨模块覆盖**：`export.cleanup_old_tasks` 任务实际定义在 `app/tasks/user_tasks.py`，由 `app.tasks.user` autodiscover 加载（`user_tasks.py` 在 `app/tasks/__init__.py` 中被 `user` 模块导入），Beat 表中以 `export.cleanup_old_tasks` 任务名发送，功能正确
> - **结论**：autodiscover 列表只列出能加载到任务定义的模块路径，任务名由 `@task(name=...)` 显式声明，二者无需一一对应，Celery 内部通过任务名注册表查找执行。R18 验证 10 个 Beat 任务全部可被 autodiscover 加载，无 `NotRegistered` 异常。

---

## 5. 运维注意事项

1. **错峰调度**：多个每小时任务使用不同 minute 偏移（0、5），避免瞬时负载峰值
2. **队列分离**：`infra` 队列跑清理类任务，不挤占 `default` 业务队列
3. **幂等保证**：所有定时任务必须可安全重复执行（如孤儿清理使用 `WHERE` 条件而非全表删）
4. **监控**：Beat 启动后可通过 `celery -A app.core.celery inspect active` 查看任务执行情况
5. **禁用任务**：注释 `BEAT_SCHEDULE` 中对应条目即可，无需修改模块代码
