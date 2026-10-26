"""
app/core/beat_schedule.py — Celery Beat 定时任务注册

依据：切片 13-infrastructure/beat_schedule.py.md
规范：所有定时任务集中注册，不在各模块分散定义
"""

from celery import Celery
from celery.schedules import crontab


def configure_beat(celery_app: Celery) -> None:
    """注册全部 Beat 定时任务"""
    celery_app.conf.beat_schedule = {
        # ---------- 文件管理 ----------
        "file-management-orphan-cleanup": {
            "task": "app.tasks.file_management.cleanup_orphan_files",
            "schedule": crontab(minute=0),  # 每小时
            "options": {"queue": "infra"},
            "description": "清理 OSS/本地存储中的孤儿文件（未关联 DB 记录）",
        },
        # ---------- 记分牌 ----------
        "scoring-cleanup-abandoned": {
            "task": "app.tasks.scoring.cleanup_abandoned_matches",
            "schedule": crontab(minute=5),  # 每小时偏移 5 分
            "options": {"queue": "default"},
            "description": "清理超时未完成的记分牌比赛（释放 Redis 序号）",
        },
        # ---------- 会员 ----------
        "membership-expiry-check": {
            "task": "app.tasks.membership.check_expiry",
            "schedule": crontab(minute=30, hour=0),  # 每天 00:30
            "options": {"queue": "default"},
            "description": "会员到期检测：active→expiring_soon→grace_period→expired→closed",
        },
        # ---------- 通知 ----------
        "notification-old-cleanup": {
            "task": "app.tasks.notification.cleanup_old_notifications",
            "schedule": crontab(minute=0, hour=2, day_of_month=1),  # 每月 1 日 02:00
            "options": {"queue": "infra"},
            "description": "清理过期通知（删除 90 天前已读 + 180 天前未读）",
        },
        "notification-training-reminder": {
            "task": "app.tasks.notification.training_reminder",
            "schedule": crontab(hour=19, minute=0),  # 每天 19:00
            "options": {"queue": "default"},
            "description": "训练提醒推送：查询 >3 天未训练用户并推送 WS + 微信订阅消息",
        },
        # ---------- AI 推理健康检查 ----------
        "ai-inference-health-check": {
            "task": "app.tasks.ai_inference_health.check_inference_health",
            "schedule": crontab(minute="*/5"),  # 每 5 分钟
            "options": {"queue": "default"},
            "description": "AI 推理服务健康探测（熔断器状态更新 + 延迟采集）",
        },
        # ---------- 游戏化 ----------
        "gamification-monthly-points-reset": {
            "task": "app.tasks.gamification.reset_monthly_points",
            "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 每月 1 日 00:00
            "options": {"queue": "default"},
            "description": "游戏化月度积分重置（保留总积分，重置月度榜）",
        },
        # ---------- 用户 ----------
        "user-account-deletion": {
            "task": "app.tasks.user.process_account_deletions",
            "schedule": crontab(minute=15),  # 每小时偏移 15 分
            "options": {"queue": "default"},
            "description": "处理用户注销请求（72h 冷静期后删除用户数据）",
        },
        # ---------- 审计日志 ----------
        "audit-log-cleanup": {
            "task": "app.tasks.audit.cleanup_old_logs",
            "schedule": crontab(minute=0, hour=3),  # 每天 03:00
            "options": {"queue": "infra"},
            "description": "清理超期审计日志（保留 180 天）",
        },
        # ---------- 导出 ----------
        "export-cleanup-old-tasks": {
            "task": "app.tasks.export.cleanup_old_tasks",
            "schedule": crontab(minute=0, hour=3),  # 每天 03:00
            "options": {"queue": "infra"},
            "description": "清理过期导出任务及临时文件（保留 7 天）",
        },
    }
