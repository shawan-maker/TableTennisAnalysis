"""预置 6 个基础徽章定义到 badge_definition 表 — R12-Gam-1

依据：切片 09-gamification/backend.md「预置徽章数据（通过 Alembic data
migration 或 seed 脚本）」。原 BADGE_SEEDS 常量零引用（死代码），生产
badge_definition 表恒空，徽章列表/解锁功能不可用。

幂等可重复执行：已存在的徽章按 seed 更新定义字段，不存在的插入。

用法：python scripts/seed_badges.py
"""
import asyncio

from app.core.database import async_session_factory
from app.services.gamification_service import BadgeService


async def main() -> None:
    async with async_session_factory() as db:
        result = await BadgeService.seed_badge_definitions(db)
        await db.commit()
    print(f"badge_definition seed result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
