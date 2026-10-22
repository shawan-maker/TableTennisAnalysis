#!/usr/bin/env python3
"""
verify_db.py — 验证数据库表和索引

检查项：
  1. 列出所有业务表
  2. 列出所有索引
  3. 检查 Alembic 版本号
  4. 统计各表行数

使用方式：
  python verify_db.py

依赖：
  pip install asyncpg

依据：docs/08部署手册/04-验证与测试.md
"""

import asyncio
import sys

# ============================================================
# 连接配置 — 与 .env 保持一致
# ============================================================
VM_HOST = "192.168.40.147"
PG_PORT = 5432
PG_USER = "tta_user"
PG_PASS = "tta_pass_dev"
PG_DB = "tta"


async def main():
    try:
        import asyncpg
    except ImportError:
        print("[ERROR] asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    print(f"Connecting to {VM_HOST}:{PG_PORT}/{PG_DB} ...\n")

    conn = await asyncpg.connect(
        host=VM_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASS,
        database=PG_DB,
    )

    # ---- Tables ----
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    print(f"Tables ({len(rows)}):")
    for r in rows:
        print(f"  {r['tablename']}")

    # ---- Indexes ----
    idx_rows = await conn.fetch(
        "SELECT indexname, tablename FROM pg_indexes "
        "WHERE schemaname='public' ORDER BY tablename, indexname"
    )
    print(f"\nIndexes ({len(idx_rows)}):")
    for r in idx_rows:
        print(f"  {r['indexname']:40s} on {r['tablename']}")

    # ---- Alembic version ----
    try:
        ver = await conn.fetch("SELECT version_num FROM alembic_version")
        print(f"\nAlembic version: {ver[0]['version_num']}")
    except Exception:
        print("\n[Alembic] No migration applied yet")

    # ---- Row counts ----
    print("\nRow counts:")
    for table_name in [r['tablename'] for r in rows if r['tablename'] != 'alembic_version']:
        count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
        print(f"  {table_name:20s} {count} rows")

    await conn.close()
    print("\n[OK] Database verification complete.")


if __name__ == "__main__":
    asyncio.run(main())
