"""列出数据库中所有表 — 开发调试用。

用法：python scripts/check_tables.py
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def check():
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))
        tables = [row[0] for row in r]
        print(f"Tables in DB ({len(tables)}):")
        for t in tables:
            print(f"  {t}")
        await engine.dispose()

asyncio.run(check())
