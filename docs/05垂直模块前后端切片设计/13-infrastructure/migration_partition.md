# 数据库分区迁移脚本 — migration_partition

> **模块名称**：`infrastructure / migration_partition`
> **定位**：高增长表的声明式分区 Alembic 迁移 + pg_cron 自动分区维护
> **依据**：SC-1 / INF-9 — 架构 §9.3 声明使用 pg_cron + 声明式分区，切片无迁移代码

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 声明式分区 | PostgreSQL 原生 `PARTITION BY RANGE (created_at)` 按月分区 |
| 自动维护 | pg_cron 每月 25 日自动创建下月分区 + 过期分区归档 |
| Alembic 集成 | 迁移脚本创建分区父表 + 初始分区 + pg_cron 作业 |
| 回滚安全 | downgrade 删除分区表不影响非分区表 |

---

## 2. 分区表清单

| 表 | 分区键 | 分区策略 | 归档策略 |
|----|--------|---------|---------|
| `video_task` | `created_at` | 按月 RANGE | 1 年前归档到 `video_task_archive` |
| `score_record` | `created_at` | 按月 RANGE | 1 年前归档 |
| `notification_record` | `created_at` | 按月 RANGE | pg_cron 3 个月 drop 旧分区 + Celery Beat 90 天清理已读记录 |

> **注意**：`analysis_report` 不分区（JSONB 较大，分区降低查询效率）；`feedback_record` / `progress_snapshot` / `technique_trend` / `plan_adjustment` 永久保留，不分区。

---

## 3. 完整实现

### Alembic 迁移脚本

```python
# alembic/versions/0200_create_partition_tables.py
"""create partition tables for video_task, score_record, notification_record

Revision ID: 0200
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0200"
down_revision = "0199"
depends_on = None


def upgrade():
    # -----------------------------------------------------------------------
    # 1. video_task — 按月分区
    # -----------------------------------------------------------------------
    # 先备份原表数据
    op.execute("CREATE TABLE video_task_nonpartition AS SELECT * FROM video_task")
    op.execute("DROP TABLE video_task")

    # 创建分区父表
    op.execute("""
        CREATE TABLE video_task (
            id BIGSERIAL,
            user_id BIGINT NOT NULL REFERENCES "user" (id),
            file_id BIGINT NOT NULL REFERENCES file_record (id),
            task_uuid VARCHAR(36) NOT NULL UNIQUE,
            oss_key VARCHAR(255) NOT NULL,
            duration_sec INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    op.create_index("idx_video_task_user", "video_task", ["user_id"])
    op.create_index("idx_video_task_status", "video_task", ["status"])
    op.create_index("idx_video_task_uuid", "video_task", ["task_uuid"])

    # 创建初始分区（当前月 + 下月）
    op.execute("""
        CREATE TABLE video_task_202610
        PARTITION OF video_task
        FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')
    """)
    op.execute("""
        CREATE TABLE video_task_202611
        PARTITION OF video_task
        FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
    """)

    # 迁回数据
    op.execute("""
        INSERT INTO video_task (user_id, file_id, task_uuid, oss_key, duration_sec, status, created_at, completed_at)
        SELECT user_id, file_id, task_uuid, oss_key, duration_sec, status, created_at, completed_at
        FROM video_task_nonpartition
    """)
    op.execute("DROP TABLE video_task_nonpartition")

    # -----------------------------------------------------------------------
    # 2. score_record — 按月分区
    # -----------------------------------------------------------------------
    op.execute("CREATE TABLE score_record_nonpartition AS SELECT * FROM score_record")
    op.execute("DROP TABLE score_record")

    op.execute("""
        CREATE TABLE score_record (
            id BIGSERIAL,
            match_id BIGINT NOT NULL REFERENCES match (id),
            sequence INTEGER NOT NULL,
            scorer VARCHAR(10) NOT NULL,
            score_method VARCHAR(32),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    op.create_index("idx_score_record_match", "score_record", ["match_id"])

    op.execute("""
        CREATE TABLE score_record_202610
        PARTITION OF score_record
        FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')
    """)
    op.execute("""
        CREATE TABLE score_record_202611
        PARTITION OF score_record
        FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
    """)

    op.execute("""
        INSERT INTO score_record (match_id, sequence, scorer, score_method, created_at)
        SELECT match_id, sequence, scorer, score_method, created_at
        FROM score_record_nonpartition
    """)
    op.execute("DROP TABLE score_record_nonpartition")

    # -----------------------------------------------------------------------
    # 3. notification_record — 按月分区
    # -----------------------------------------------------------------------
    op.execute("CREATE TABLE notification_record_nonpartition AS SELECT * FROM notification_record")
    op.execute("DROP TABLE notification_record")

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
    op.create_index("idx_notif_user_unread", "notification_record", ["user_id", "is_read"])

    op.execute("""
        CREATE TABLE notification_record_202610
        PARTITION OF notification_record
        FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')
    """)
    op.execute("""
        CREATE TABLE notification_record_202611
        PARTITION OF notification_record
        FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
    """)

    op.execute("""
        INSERT INTO notification_record (user_id, type, title, content, is_read, created_at)
        SELECT user_id, type, title, content, is_read, created_at
        FROM notification_record_nonpartition
    """)
    op.execute("DROP TABLE notification_record_nonpartition")

    # -----------------------------------------------------------------------
    # 4. 注册 pg_cron 扩展 + 定时作业
    # -----------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")

    # 每月 25 日 02:00 创建下月分区
    op.execute("""
        SELECT cron.schedule(
            'create_next_month_partitions',
            '0 2 25 * *',
            $$
            SELECT create_next_month_partitions();
            $$
        )
    """)

    # 每月 1 日 03:00 归档过期分区（1 年前）
    op.execute("""
        SELECT cron.schedule(
            'archive_old_partitions',
            '0 3 1 * *',
            $$
            SELECT archive_old_partitions(12);
            $$
        )
    """)

    # notification_record 分区生命周期管理（pg_cron 3 个月 drop 旧分区）
    # 已读通知记录 90 天清理由 Celery Beat 统一调度（见 beat_schedule.py）
    op.execute("""
        SELECT cron.schedule(
            'cleanup_old_notifications',
            '0 4 1 * *',
            $$
            SELECT cleanup_old_notification_partitions(3);
            $$
        )
    """)


def downgrade():
    # 回滚：取消 pg_cron 作业
    op.execute("SELECT cron.unschedule('create_next_month_partitions')")
    op.execute("SELECT cron.unschedule('archive_old_partitions')")
    op.execute("SELECT cron.unschedule('cleanup_old_notifications')")

    # 回滚：将分区表改回普通表（简化版，生产环境需谨慎）
    for table in ["video_task", "score_record", "notification_record"]:
        op.execute(f"CREATE TABLE {table}_backup AS SELECT * FROM {table}")
        op.execute(f"DROP TABLE {table}")
        op.execute(f"CREATE TABLE {table} AS SELECT * FROM {table}_backup")
        op.execute(f"DROP TABLE {table}_backup")
```

### 分区维护函数

```python
# alembic/versions/0200_create_partition_tables.py (续)

"""
分区维护函数（在 upgrade 中创建）
"""


def create_partition_maintenance_functions():
    """在 upgrade() 末尾调用，创建分区维护函数。"""
    op.execute("""
        CREATE OR REPLACE FUNCTION create_next_month_partitions()
        RETURNS void AS $$
        DECLARE
            next_month_start DATE;
            next_month_end DATE;
            partition_suffix TEXT;
            table_name TEXT;
            partition_table TEXT;
        BEGIN
            next_month_start := date_trunc('month', CURRENT_DATE + INTERVAL '1 month');
            next_month_end := next_month_start + INTERVAL '1 month';
            partition_suffix := to_char(next_month_start, 'YYYYMM');

            FOR table_name IN
                SELECT unnest(ARRAY['video_task', 'score_record', 'notification_record'])
            LOOP
                partition_table := table_name || '_' || partition_suffix;
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                    partition_table, table_name, next_month_start, next_month_end
                );
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION archive_old_partitions(retention_months INT)
        RETURNS void AS $$
        DECLARE
            cutoff_date DATE;
            old_partition TEXT;
            table_name TEXT;
        BEGIN
            cutoff_date := date_trunc('month', CURRENT_DATE - (retention_months || ' months')::INTERVAL);

            FOR table_name IN
                SELECT unnest(ARRAY['video_task', 'score_record'])
            LOOP
                FOR old_partition IN
                    SELECT tablename FROM pg_tables
                    WHERE tablename LIKE table_name || '_20%'
                    AND tablename != table_name || '_' || to_char(cutoff_date, 'YYYYMM')
                LOOP
                    -- 归档到冷表（仅 video_task）
                    IF table_name = 'video_task' THEN
                        EXECUTE format(
                            'INSERT INTO video_task_archive SELECT * FROM %I ON CONFLICT DO NOTHING',
                            old_partition
                        );
                    END IF;
                    -- DETACH 分区并删除
                    EXECUTE format('DROP TABLE IF EXISTS %I', old_partition);
                END LOOP;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_old_notification_partitions(retention_months INT)
        RETURNS void AS $$
        DECLARE
            cutoff_date DATE;
            old_partition TEXT;
        BEGIN
            cutoff_date := date_trunc('month', CURRENT_DATE - (retention_months || ' months')::INTERVAL);

            FOR old_partition IN
                SELECT tablename FROM pg_tables
                WHERE tablename LIKE 'notification_record_20%'
                AND tablename < 'notification_record_' || to_char(cutoff_date, 'YYYYMM')
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I', old_partition);
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)
```

---

## 4. 查询注意事项

```python
# 03-video_analysis/backend.md (Service 层查询示例)
"""分区表查询须包含分区键以触发分区裁剪（Partition Pruning）。"""

# ✅ 正确：包含 created_at 范围条件，触发分区裁剪
stmt = (
    select(VideoTask)
    .where(VideoTask.user_id == user_id)
    .where(VideoTask.created_at >= start_date)
    .where(VideoTask.created_at < end_date)
    .order_by(VideoTask.created_at.desc())
    .limit(20)
)

# ❌ 错误：不含 created_at 条件，扫描全部分区
stmt = (
    select(VideoTask)
    .where(VideoTask.user_id == user_id)
    .order_by(VideoTask.created_at.desc())
    .limit(20)
)
```

> **Anti-hallucination 约束**：
> 1. 分区表的主键必须包含分区键（`PRIMARY KEY (id, created_at)`）
> 2. 所有查询分区表的 SQL 必须包含 `created_at` 范围条件以触发分区裁剪
> 3. pg_cron 作业创建后需在 `cron.job` 表中验证调度状态
> 4. `video_task_archive` 冷表为普通表（非分区），仅在归档时写入，不在线查询
