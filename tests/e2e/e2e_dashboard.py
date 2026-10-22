"""
S3 data_dashboard 端到端验证脚本

验证流程：
1. 健康检查 + OpenAPI 路径数
2. 创建用户 + JWT
3. 创建比赛记录 + 分析报告（测试数据）
4. 5 个 dashboard 端点验证
5. 缓存命中验证
6. 未授权访问验证
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.core.database import async_session_factory
from app.core.security import create_access_token, generate_jti
from app.models.user import User
from app.models.match import MatchRecord
from app.models.video_analysis import FileRecord, VideoTask, AnalysisReport

import httpx

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/v1"
checks_passed = 0
checks_failed = 0


def check(condition, name):
    global checks_passed, checks_failed
    if condition:
        checks_passed += 1
        print(f"  ✅ {name}")
    else:
        checks_failed += 1
        print(f"  ❌ {name}")


async def main():
    global checks_passed, checks_failed

    print("=" * 60)
    print("Dashboard uvicorn 端到端验证")
    print("=" * 60)

    # 1. 健康检查
    print("\n--- 1. 健康检查 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/health")
        check(resp.status_code == 200, "GET /health → 200")
        check(resp.json()["status"] == "ok", "health status=ok")

        # OpenAPI 路径数
        resp = await client.get("/openapi.json")
        paths = resp.json()["paths"]
        check(len(paths) >= 45, f"OpenAPI paths >= 45 (actual: {len(paths)})")

        # 验证 dashboard 端点存在
        dashboard_paths = [p for p in paths if "/dashboard" in p]
        check(len(dashboard_paths) >= 5, f"Dashboard endpoints >= 5 (actual: {len(dashboard_paths)})")
        print(f"  Dashboard paths: {dashboard_paths}")

    # 2. 创建测试用户 + JWT + 测试数据
    print("\n--- 2. 创建用户 + JWT + 测试数据 ---")
    async with async_session_factory() as db:
        # 清理旧数据
        await db.execute(text("DELETE FROM feedback_record"))
        await db.execute(text("DELETE FROM share_record"))
        await db.execute(text("DELETE FROM analysis_report"))
        await db.execute(text("DELETE FROM pipeline_step"))
        await db.execute(text("DELETE FROM video_task"))
        await db.execute(text("DELETE FROM file_record"))
        await db.execute(text("DELETE FROM match_record"))
        await db.execute(text("DELETE FROM \"user\" WHERE openid LIKE 'e2e_dash_%'"))
        await db.commit()

        user = User(
            openid="e2e_dash_user_001",
            nickname="Dashboard测试用户",
            avatar_url="https://example.com/avatar.png",
            status="active",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
        print(f"  user_id={user_id}")

        # 创建 3 场比赛（2 胜 1 负）
        now = datetime.now(timezone.utc)
        for i, (my, opp, is_win) in enumerate([(3, 1, True), (3, 0, True), (1, 3, False)]):
            record = MatchRecord(
                user_id=user_id,
                opponent_name=f"对手{i+1}",
                opponent_rating=1500 + i,
                my_score=my,
                opponent_score=opp,
                is_win=is_win,
                format="bo5",
                match_type="friendly",
                match_date=now - timedelta(days=i),
            )
            db.add(record)

        # 创建 2 份分析报告
        for i in range(2):
            file_record = FileRecord(
                user_id=user_id,
                oss_key=f"e2e_dash/key{i}",
                file_size=10 * 1024 * 1024,
                file_type="mp4",
                status="uploaded",
            )
            db.add(file_record)
            await db.flush()

            task = VideoTask(
                user_id=user_id,
                file_id=file_record.id,
                oss_key=f"e2e_dash/key{i}",
                status="completed",
                task_uuid=f"e2e-dash-uuid-{i}",
                progress=100,
            )
            db.add(task)
            await db.flush()

            report = AnalysisReport(
                task_id=task.id,
                user_id=user_id,
                result_data={
                    "technique_distribution": {
                        "forehand_drive": 45 + i * 5,
                        "backhand_drive": 18 + i * 3,
                        "forehand_loop": 12,
                        "serve": 23,
                    },
                    "landing_heatmap": {
                        "nine_grid": [[2+i, 5, 3], [4, 8, 6], [1, 3, 2+i]],
                    },
                    "metrics": {
                        "landing_forehand_pct": 0.68,
                        "landing_backhand_pct": 0.25,
                        "landing_middle_pct": 0.07,
                    },
                },
                report_text={
                    "summary": f"第{i+1}份报告摘要",
                    "issues": ["反手使用率偏低"] if i == 0 else [],
                    "suggestions": ["增加反手练习"],
                },
                is_llm_generated=False,
                created_at=now - timedelta(days=i),
            )
            db.add(report)

        await db.commit()
        print("  已创建 3 场比赛 + 2 份分析报告")

    token = create_access_token({"sub": str(user_id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Dashboard 端点验证
    print("\n--- 3. Dashboard 端点验证 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # Overview
        print("\n  GET /dashboard/overview")
        resp = await client.get(f"{API_PREFIX}/dashboard/overview", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/overview → 200")
        data = resp.json()["data"]
        check(data["wins"] == 2, f"overview wins=2 (actual: {data.get('wins')})")
        check(data["losses"] == 1, f"overview losses=1 (actual: {data.get('losses')})")
        check(data["analysis_count"] == 2, f"overview analysis_count=2 (actual: {data.get('analysis_count')})")
        check(abs(data["win_rate"] - 0.67) < 0.01, f"overview win_rate≈0.67 (actual: {data.get('win_rate')})")
        check(data["streak_days"] == 0, f"overview streak_days=0 (actual: {data.get('streak_days')})")
        check(data["latest_advice_summary"] is not None, "overview latest_advice_summary is not None")
        check(data["trend"] in ("up", "down", "flat"), f"overview trend valid (actual: {data.get('trend')})")

        # Win-rate-trend
        print("\n  GET /dashboard/win-rate-trend?period=month")
        resp = await client.get(f"{API_PREFIX}/dashboard/win-rate-trend?period=month", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/win-rate-trend → 200")
        data = resp.json()["data"]
        check(len(data["labels"]) > 0, f"trend labels>0 (actual: {len(data.get('labels', []))})")
        check(len(data["series"]) == 2, f"trend series=2 (actual: {len(data.get('series', []))})")
        check(data["series"][0]["name"] == "胜率", f"trend series[0] name=胜率 (actual: {data['series'][0]['name']})")

        # Technique-stats
        print("\n  GET /dashboard/technique-stats")
        resp = await client.get(f"{API_PREFIX}/dashboard/technique-stats", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/technique-stats → 200")
        data = resp.json()["data"]
        check(len(data["technique_distribution"]) == 4, f"technique dist=4 items (actual: {len(data.get('technique_distribution', []))})")
        names = [item["name"] for item in data["technique_distribution"]]
        check("正手攻球" in names, f"technique has 正手攻球 (names: {names})")
        check("发球" in names, f"technique has 发球 (names: {names})")

        # Landing-heatmap
        print("\n  GET /dashboard/landing-heatmap")
        resp = await client.get(f"{API_PREFIX}/dashboard/landing-heatmap", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/landing-heatmap → 200")
        data = resp.json()["data"]
        check(len(data["nine_grid"]) == 3, f"heatmap 3x3 grid (actual: {len(data.get('nine_grid', []))})")
        check(data["source_reports_count"] == 2, f"heatmap source=2 (actual: {data.get('source_reports_count')})")
        check(data["total_rallies"] > 0, f"heatmap rallies>0 (actual: {data.get('total_rallies')})")
        check("forehand" in data["distribution"], "heatmap distribution has forehand")

        # Match-records
        print("\n  GET /dashboard/match-records?page=1&page_size=20")
        resp = await client.get(f"{API_PREFIX}/dashboard/match-records?page=1&page_size=20", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/match-records → 200")
        data = resp.json()["data"]
        check(data["total"] == 3, f"records total=3 (actual: {data.get('total')})")
        check(len(data["items"]) == 3, f"records items=3 (actual: {len(data.get('items', []))})")

        # Match-records filter=win
        print("\n  GET /dashboard/match-records?result=win")
        resp = await client.get(f"{API_PREFIX}/dashboard/match-records?result=win", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/match-records?result=win → 200")
        data = resp.json()["data"]
        check(data["total"] == 2, f"records win total=2 (actual: {data.get('total')})")
        check(all(item["is_win"] for item in data["items"]), "all items is_win=True")

        # Match-records filter=lose
        print("\n  GET /dashboard/match-records?result=lose")
        resp = await client.get(f"{API_PREFIX}/dashboard/match-records?result=lose", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/match-records?result=lose → 200")
        data = resp.json()["data"]
        check(data["total"] == 1, f"records lose total=1 (actual: {data.get('total')})")

        # period=quarter
        print("\n  GET /dashboard/win-rate-trend?period=quarter")
        resp = await client.get(f"{API_PREFIX}/dashboard/win-rate-trend?period=quarter", headers=headers)
        check(resp.status_code == 200, "GET /dashboard/win-rate-trend?period=quarter → 200")

    # 4. 缓存验证
    print("\n--- 4. 缓存策略验证 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # 第二次 overview — 缓存命中
        resp1 = await client.get(f"{API_PREFIX}/dashboard/overview", headers=headers)
        resp2 = await client.get(f"{API_PREFIX}/dashboard/overview", headers=headers)
        check(resp1.status_code == 200 and resp2.status_code == 200, "两次 overview 请求均 200")
        check(resp1.json()["data"] == resp2.json()["data"], "缓存命中 — 两次返回相同数据")

    # 5. 权限验证
    print("\n--- 5. 权限验证 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(f"{API_PREFIX}/dashboard/overview")
        check(resp.status_code == 401, f"未授权 overview → 401 (actual: {resp.status_code})")

        resp = await client.get(f"{API_PREFIX}/dashboard/technique-stats")
        check(resp.status_code == 401, f"未授权 technique-stats → 401 (actual: {resp.status_code})")

        resp = await client.get(f"{API_PREFIX}/dashboard/match-records")
        check(resp.status_code == 401, f"未授权 match-records → 401 (actual: {resp.status_code})")

    # 6. 空用户验证
    print("\n--- 6. 空用户概览验证 ---")
    async with async_session_factory() as db:
        empty_user = User(
            openid="e2e_dash_empty",
            nickname="空用户",
            status="active",
        )
        db.add(empty_user)
        await db.commit()
        await db.refresh(empty_user)
        empty_token = create_access_token({"sub": str(empty_user.id), "jti": generate_jti()})

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        empty_headers = {"Authorization": f"Bearer {empty_token}"}
        resp = await client.get(f"{API_PREFIX}/dashboard/overview", headers=empty_headers)
        check(resp.status_code == 200, "空用户 overview → 200")
        data = resp.json()["data"]
        check(data["wins"] == 0, f"空用户 wins=0 (actual: {data.get('wins')})")
        check(data["losses"] == 0, f"空用户 losses=0 (actual: {data.get('losses')})")
        check(data["analysis_count"] == 0, f"空用户 analysis_count=0 (actual: {data.get('analysis_count')})")
        check(data["latest_advice_summary"] is None, "空用户 latest_advice_summary=None")

        resp = await client.get(f"{API_PREFIX}/dashboard/technique-stats", headers=empty_headers)
        check(resp.status_code == 200, "空用户 technique-stats → 200")
        check(len(resp.json()["data"]["technique_distribution"]) == 0, "空用户 technique dist=0 items")

        resp = await client.get(f"{API_PREFIX}/dashboard/landing-heatmap", headers=empty_headers)
        check(resp.status_code == 200, "空用户 landing-heatmap → 200")
        check(resp.json()["data"]["source_reports_count"] == 0, "空用户 heatmap source=0")

    # 清理
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM feedback_record"))
        await db.execute(text("DELETE FROM share_record"))
        await db.execute(text("DELETE FROM analysis_report"))
        await db.execute(text("DELETE FROM pipeline_step"))
        await db.execute(text("DELETE FROM video_task"))
        await db.execute(text("DELETE FROM file_record"))
        await db.execute(text("DELETE FROM match_record"))
        await db.execute(text("DELETE FROM \"user\" WHERE openid LIKE 'e2e_dash_%'"))
        await db.commit()

    # 清理 Redis 缓存
    from app.core.redis import get_redis
    redis = await get_redis()
    for key in await redis.keys("dashboard:*"):
        await redis.delete(key)

    # 汇总
    print("\n" + "=" * 60)
    print(f"Dashboard E2E: {checks_passed}/{checks_passed + checks_failed} PASSED")
    if checks_failed == 0:
        print("ALL PASSED ✅")
    else:
        print(f"FAILED: {checks_failed} checks")
    print("=" * 60)

    return checks_failed


if __name__ == "__main__":
    failed = asyncio.run(main())
    sys.exit(1 if failed else 0)
