"""partition notification_record by month

Revision ID: a1b2c3d4e5f6
Revises: 0c7549d8c42d
Create Date: 2026-10-23 12:00:00

分区策略：
- notification_record 按月 RANGE 分区 (created_at)
- pg_cron 自动创建下月分区 + 3 个月 drop 旧分区
- Celery Beat 90 天清理已读通知

注意：此迁移将 notification_record 从普通表转为分区表。
如果表中已有数据，会先备份再迁移。
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta

revision = "a1b2c3d4e5f6"
down_revision = "0c7549d8c42d"
branch_labels = None
depends_on = None


def _month_range(offset: int = 0) -> tuple[str, str, str]:
    """生成 offset 月后的月份范围 (start, end, suffix)"""
    now = datetime.utcnow()
    year = now.year
    month = now.month + offset
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    start = f"{year:04d}-{month:02d}-01"
    # 下月
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_year += 1
        next_month = 1
    end = f"{next_year:04d}-{next_month:02d}-01"
    suffix = f"{year:04d}{month:02d}"
    return start, end, suffix


def _pg_cron_installable(conn) -> bool:
    """检查 pg_cron 扩展是否可安装（未安装该扩展的环境如 GitHub Actions
    postgres:15 服务容器 / 本地开发 VM 会跳过定时任务配置，不影响分区表本体）"""
    result = conn.execute(sa.text(
        "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_cron'"
    ))
    return result.scalar() == 1


def _pg_cron_installed(conn) -> bool:
    """检查 pg_cron 扩展是否已安装（用于 downgrade 时安全反注册）"""
    result = conn.execute(sa.text(
        "SELECT count(*) FROM pg_extension WHERE extname = 'pg_cron'"
    ))
    return result.scalar() == 1


def upgrade() -> None:
    # 检查 notification_record 是否已经是分区表
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT partstrat FROM pg_partitioned_table pt "
        "JOIN pg_class c ON pt.partrelid = c.oid "
        "WHERE c.relname = 'notification_record'"
    ))
    if result.fetchone():
        # 已经是分区表，跳过
        print("notification_record 已是分区表，跳过迁移")
        return

    # 1. 备份现有数据
    op.execute("CREATE TABLE notification_record_backup AS SELECT * FROM notification_record")
    op.execute("DROP TABLE notification_record")

    # 2. 创建分区父表
    op.execute("""
        CREATE TABLE notification_record (
            id BIGSERIAL,
            user_id BIGINT NOT NULL REFERENCES "user" (id),
            type VARCHAR(50) NOT NULL,
            title VARCHAR(200) NOT NULL,
            content TEXT,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # 3. 创建索引
    op.create_index("idx_notif_user_unread", "notification_record", ["user_id", "is_read"])
    op.create_index("idx_notif_user_created", "notification_record", ["user_id", "created_at"])

    # 4. 创建当前月和下月分区
    for offset in [0, 1]:
        start, end, suffix = _month_range(offset)
        op.execute(f"""
            CREATE TABLE notification_record_{suffix}
            PARTITION OF notification_record
            FOR VALUES FROM ('{start}') TO ('{end}')
        """)

    # 5. 迁移备份数据
    op.execute("""
        INSERT INTO notification_record (user_id, type, title, content, is_read, created_at)
        SELECT user_id, type, title, content, is_read, created_at
        FROM notification_record_backup
    """)

    # 6. 删除备份表
    op.execute("DROP TABLE notification_record_backup")

    # 7-9. pg_cron 定时分区维护任务（仅在环境支持 pg_cron 时配置；
    #      未安装 pg_cron 的环境如 CI 容器/开发 VM 跳过，分区表本体不受影响，
    #      生产环境须自行保证 pg_cron 可用或手动创建后续月分区）
    if not _pg_cron_installable(conn):
        print("警告: pg_cron 扩展不可安装，跳过分区自动维护任务 "
              "（后续月分区需手动创建或安装 pg_cron 后重放本迁移）")
        return

    # 7. 创建 pg_cron 扩展（如果不存在）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")

    # 8. 创建 pg_cron job: 每月25日自动创建下月分区
    next_month_start, next_month_end, next_suffix = _month_range(1)
    op.execute(f"""
        SELECT cron.schedule(
            'create_notification_partition_monthly',
            '0 0 25 * *',
            $$CREATE TABLE IF NOT EXISTS notification_record_{next_suffix}
              PARTITION OF notification_record
              FOR VALUES FROM ('{next_month_start}') TO ('{next_month_end}')$$
        )
    """)

    # 9. 创建 pg_cron job: 每月1日清理3个月前分区
    old_start, old_end, old_suffix = _month_range(-3)
    op.execute(f"""
        SELECT cron.schedule(
            'drop_old_notification_partition',
            '0 0 1 * *',
            $$DROP TABLE IF EXISTS notification_record_{old_suffix}$$
        )
    """)


def downgrade() -> None:
    # 取消 pg_cron jobs（仅在扩展已安装时执行；job 不存在时容忍失败）
    conn = op.get_bind()
    if _pg_cron_installed(conn):
        for job in ("create_notification_partition_monthly", "drop_old_notification_partition"):
            try:
                op.execute(sa.text(f"SELECT cron.unschedule('{job}')"))
            except Exception as exc:  # noqa: BLE001 — job 不存在时容忍
                print(f"警告: cron.unschedule('{job}') 失败（可忽略）: {exc}")

    # 备份分区数据
    op.execute("CREATE TABLE notification_record_backup AS SELECT * FROM notification_record")

    # 删除分区表
    op.execute("DROP TABLE notification_record CASCADE")

    # 重建普通表
    op.execute("""
        CREATE TABLE notification_record (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES "user" (id),
            type VARCHAR(50) NOT NULL,
            title VARCHAR(200) NOT NULL,
            content TEXT,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 恢复数据
    op.execute("""
        INSERT INTO notification_record (user_id, type, title, content, is_read, created_at)
        SELECT user_id, type, title, content, is_read, created_at
        FROM notification_record_backup
    """)
    op.execute("DROP TABLE notification_record_backup")

    op.create_index("idx_notif_user_unread", "notification_record", ["user_id", "is_read"])
    op.create_index("idx_notif_user_created", "notification_record", ["user_id", "created_at"])
