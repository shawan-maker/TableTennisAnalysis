"""
tmp/e2e_s3.py — S3 uvicorn 端到端验证脚本

验证流程：
1. 健康检查 + OpenAPI 路径数
2. 创建用户 + JWT
3. 上传凭证 → mock 文件 → 确认上传
4. 创建任务 → 流水线执行 → 任务完成
5. 报告列表 + 详情
6. 反馈提交
7. 标注视频
8. 分享创建 + 公开访问
9. 配额限制
"""

import asyncio
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import select, text
from app.core.database import async_session_factory, engine
from app.core.security import create_access_token, generate_jti
from app.models.user import User
from app.services.file_service import FileService

import httpx

BASE_URL = "http://127.0.0.1:8000"
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
    print("S3 uvicorn 端到端验证")
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
        check(len(paths) >= 30, f"OpenAPI paths >= 30 (actual: {len(paths)})")

        # 验证 S3 端点存在
        s3_paths = [p for p in paths if "/video-analysis" in p]
        check(len(s3_paths) >= 10, f"S3 endpoints >= 10 (actual: {len(s3_paths)})")
        print(f"  S3 paths: {s3_paths}")

    # 2. 创建测试用户 + JWT
    print("\n--- 2. 创建用户 + JWT ---")
    async with async_session_factory() as db:
        # 清理旧测试数据
        await db.execute(text("DELETE FROM feedback_record"))
        await db.execute(text("DELETE FROM share_record"))
        await db.execute(text("DELETE FROM analysis_report"))
        await db.execute(text("DELETE FROM pipeline_step"))
        await db.execute(text("DELETE FROM video_task"))
        await db.execute(text("DELETE FROM file_record"))
        await db.execute(text("DELETE FROM \"user\" WHERE openid LIKE 'e2e_s3_%'"))
        await db.commit()

        user = User(
            openid="e2e_s3_user_001",
            nickname="S3测试用户",
            avatar_url="https://example.com/avatar.png",
            status="active",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
        print(f"  user_id={user_id}")

    token = create_access_token({"sub": str(user_id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}
    print(f"  token={token[:20]}...")

    # 3. 上传流程
    print("\n--- 3. 上传凭证 → mock 文件 → 确认上传 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # 上传凭证
        resp = await client.post(
            "/api/v1/video-analysis/upload-token",
            json={"filename": "match.mp4", "file_size": 10 * 1024 * 1024},
            headers=headers,
        )
        check(resp.status_code == 200, "POST /upload-token → 200")
        data = resp.json()["data"]
        file_id = data["file_id"]
        oss_key = data["oss_key"]
        check(oss_key.startswith("videos/raw/"), f"oss_key format OK: {oss_key}")

        # 保存 mock 文件
        FileService.save_uploaded_file(oss_key, b"fake_video_data" * 655360)

        # 确认上传
        resp = await client.post(
            "/api/v1/video-analysis/upload-complete",
            json={"file_id": file_id},
            headers=headers,
        )
        check(resp.status_code == 200, "POST /upload-complete → 200")
        check(resp.json()["data"]["ready"] is True, "upload confirmed ready=True")

    # 4. 创建任务 + 流水线
    print("\n--- 4. 创建任务 → 流水线执行 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        resp = await client.post(
            "/api/v1/video-analysis/tasks",
            json={"file_id": file_id},
            headers=headers,
        )
        check(resp.status_code == 200, "POST /tasks → 200")
        task_id = resp.json()["data"]["task_id"]
        print(f"  task_id={task_id}")

        # 验证任务已完成
        resp = await client.get(
            f"/api/v1/video-analysis/tasks/{task_id}",
            headers=headers,
        )
        check(resp.status_code == 200, "GET /tasks/{id} → 200")
        task_data = resp.json()["data"]
        check(task_data["status"] == "completed", f"task status=completed (actual: {task_data['status']})")
        check(task_data["progress"] == 100, f"task progress=100 (actual: {task_data['progress']})")
        check(task_data["report_id"] is not None, f"report_id exists (actual: {task_data['report_id']})")
        report_id = task_data["report_id"]

    # 5. 报告
    print("\n--- 5. 报告列表 + 详情 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            "/api/v1/video-analysis/reports?page=1&page_size=10",
            headers=headers,
        )
        check(resp.status_code == 200, "GET /reports → 200")
        check(resp.json()["data"]["total"] >= 1, "reports total >= 1")

        resp = await client.get(
            f"/api/v1/video-analysis/reports/{report_id}",
            headers=headers,
        )
        check(resp.status_code == 200, "GET /reports/{id} → 200")
        report_data = resp.json()["data"]
        check("summary" in report_data["report_text"], "report_text has summary")
        check("issues" in report_data["report_text"], "report_text has issues")
        check("technique_stats" in report_data["result_data"], "result_data has technique_stats")
        check("landing_points" in report_data["result_data"], "result_data has landing_points")
        check(report_data["is_llm_generated"] is False, "is_llm_generated=False (rule engine)")

    # 6. 反馈
    print("\n--- 6. 反馈 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            f"/api/v1/video-analysis/reports/{report_id}/feedback",
            json={"is_correct": False, "comment": "落点不太准"},
            headers=headers,
        )
        check(resp.status_code == 200, "POST feedback → 200")
        check(resp.json()["data"]["data_flywheel_action"] == "manual_review", "feedback → manual_review")

        # 覆盖更新
        resp = await client.post(
            f"/api/v1/video-analysis/reports/{report_id}/feedback",
            json={"is_correct": True},
            headers=headers,
        )
        check(resp.status_code == 200, "POST feedback update → 200")
        check(resp.json()["data"]["data_flywheel_action"] == "archived", "feedback update → archived")

    # 7. 标注视频
    print("\n--- 7. 标注视频 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            f"/api/v1/video-analysis/reports/{report_id}/annotated-video",
            headers=headers,
        )
        check(resp.status_code == 200, "GET /annotated-video → 200")
        check(resp.json()["data"]["annotated_video_url"].startswith("http"), "annotated_video_url starts with http")

    # 8. 分享
    print("\n--- 8. 分享 ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            f"/api/v1/video-analysis/reports/{report_id}/share",
            headers=headers,
        )
        check(resp.status_code == 200, "POST /share → 200")
        share_url = resp.json()["data"]["share_url"]
        share_token = share_url.split("/share/")[-1]

        # 公开访问（无认证）
        resp = await client.get(f"/api/v1/video-analysis/share/{share_token}")
        check(resp.status_code == 200, "GET /share/{token} (public) → 200")
        shared_data = resp.json()["data"]
        check("summary" in shared_data["report_text"], "shared report has summary")
        check(len(shared_data["report_text"].get("issues", [])) <= 2, "shared report issues <= 2")

        # 无效 token
        resp = await client.get("/api/v1/video-analysis/share/invalid_token")
        check(resp.status_code == 404, "GET /share/invalid → 404")

    # 9. 配额限制
    print("\n--- 9. 配额限制 ---")
    from app.core.redis import get_redis
    redis = await get_redis()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    quota_key = f"quota:analysis:{user_id}:{today}"
    await redis.set(quota_key, 3)  # 预填充到上限

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/api/v1/video-analysis/tasks",
            json={"file_id": file_id},
            headers=headers,
        )
        check(resp.status_code == 429, f"quota exhausted → 429 (actual: {resp.status_code})")

    # 清理配额
    await redis.delete(quota_key)

    # 总结
    print("\n" + "=" * 60)
    print(f"结果: {checks_passed} passed, {checks_failed} failed")
    print("=" * 60)

    # 清理测试数据
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM feedback_record"))
        await db.execute(text("DELETE FROM share_record"))
        await db.execute(text("DELETE FROM analysis_report"))
        await db.execute(text("DELETE FROM pipeline_step"))
        await db.execute(text("DELETE FROM video_task"))
        await db.execute(text("DELETE FROM file_record"))
        await db.execute(text("DELETE FROM \"user\" WHERE openid LIKE 'e2e_s3_%'"))
        await db.commit()

    await engine.dispose()

    return checks_failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
