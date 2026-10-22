#!/usr/bin/env python3
"""
test_connectivity.py — 测试本机到虚拟机的 PG/Redis 连接

使用方式：
  python test_connectivity.py

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
REDIS_PORT = 6379

PG_USER = "tta_user"
PG_PASS = "tta_pass_dev"
PG_DB = "tta"

REDIS_PASS = "redis_dev_pass"


async def test_pg():
    """Test PostgreSQL connectivity."""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=VM_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASS,
            database=PG_DB,
            timeout=10,
        )
        version = await conn.fetchval("SELECT version();")
        print(f"[PG OK]     {version}")
        await conn.close()
        return True
    except Exception as e:
        print(f"[PG FAIL]   {e}")
        return False


async def test_redis():
    """Test Redis connectivity."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=VM_HOST,
            port=REDIS_PORT,
            password=REDIS_PASS,
            socket_connect_timeout=10,
        )
        pong = await r.ping()
        print(f"[Redis OK]  PONG={pong}")
        await r.aclose()
        return True
    except Exception as e:
        print(f"[Redis FAIL] {e}")
        return False


async def main():
    print(f"Testing connectivity to VM {VM_HOST}...\n")

    pg_ok = await test_pg()
    redis_ok = await test_redis()

    status = "OK" if pg_ok else "FAIL"
    status2 = "OK" if redis_ok else "FAIL"
    print(f"\nSummary: PG={status}  Redis={status2}")

    if not (pg_ok and redis_ok):
        print("\n[Tips]")
        print("  1. Check VM is running and Docker containers are healthy")
        print(f"  2. Check firewall allows ports {PG_PORT} and {REDIS_PORT}")
        print(f"  3. Run: python docs/08部署手册/scripts/vm_deploy.py to (re)deploy")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
