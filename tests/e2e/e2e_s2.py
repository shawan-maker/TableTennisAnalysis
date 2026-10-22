"""
S2 端到端 API 验证脚本
覆盖：创建用户→生成JWT→创建比赛→列表→详情→开始→记分→撤销→结束→统计→放弃→恢复
     →match-data 快速录入→详细录入→列表→详情→编辑→无认证检查
"""
import asyncio
import httpx
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session_factory
from app.core.security import create_access_token, generate_jti
from app.models.user import User

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0

def check(label, resp, expected_status=200, key_fields=None):
    global passed, failed
    status_ok = resp.status_code == expected_status
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

    fields_ok = True
    if status_ok and key_fields:
        data = body.get("data", body)
        if isinstance(data, dict):
            for k, v in key_fields.items():
                actual = data.get(k)
                if actual != v:
                    fields_ok = False
                    print(f"  [WARN] field '{k}': expected={v}, got={actual}")

    if status_ok and fields_ok:
        passed += 1
        print(f"  [PASS] {label} ({resp.status_code})")
    else:
        failed += 1
        print(f"  [FAIL] {label} (status={resp.status_code}, expected={expected_status})")
        print(f"         body={json.dumps(body, ensure_ascii=False)[:300]}")
    return body


async def setup_user():
    """直接在 DB 中创建用户并生成 JWT（如已存在则复用）"""
    from sqlalchemy import select
    async with async_session_factory() as session:
        # 先查询是否已存在
        result = await session.execute(
            select(User).where(User.openid == "e2e_openid_001")
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                openid="e2e_openid_001",
                nickname="E2E测试员",
                avatar_url="https://example.com/avatar.png",
                status="active",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        print(f"  user_id={user.id}, token={token[:30]}...")
        return token, user.id


async def main():
    # ---- 0. 创建用户+JWT ----
    print("\n=== 0. Setup User ===")
    token, user_id = await setup_user()
    headers = {"Authorization": f"Bearer {token}"}

    client = httpx.Client(base_url=BASE, timeout=10)

    # ---- 1. 健康检查 ----
    print("\n=== 1. Health Check ===")
    r = client.get("/health")
    check("GET /health", r, 200, {"status": "ok"})

    # ---- 2. 创建比赛 ----
    print("\n=== 2. Create Match ===")
    r = client.post("/api/v1/scoring/matches", json={
        "opponent_name": "樊振东",
        "opponent_rating": 2800,
        "format": "bo5",
        "match_type": "friendly",
        "target_score": 11,
    }, headers=headers)
    body = check("POST /matches", r, 200)
    match_id = body["data"]["match_id"]
    print(f"  match_id={match_id}, status={body['data']['status']}")

    # ---- 3. 比赛列表 ----
    print("\n=== 3. Match List ===")
    r = client.get("/api/v1/scoring/matches", headers=headers)
    body = check("GET /matches (list)", r, 200)
    items = body["data"]["items"]
    print(f"  total={len(items)} matches")

    # ---- 4. 比赛详情 ----
    print("\n=== 4. Match Detail ===")
    r = client.get(f"/api/v1/scoring/matches/{match_id}", headers=headers)
    body = check("GET /matches/{id} (detail)", r, 200)
    print(f"  status={body['data']['status']}, opponent={body['data']['opponent_name']}")

    # ---- 5. 开始比赛 ----
    print("\n=== 5. Start Match ===")
    r = client.post(f"/api/v1/scoring/matches/{match_id}/start", headers=headers)
    body = check("POST /start", r, 200)
    print(f"  status={body['data']['status']}")

    # ---- 6. 记分（user 得分 x5）----
    print("\n=== 6. Score user x5 ===")
    for i in range(5):
        r = client.post(f"/api/v1/scoring/matches/{match_id}/score", json={
            "scorer": "user",
            "score_method": "rally_point",
        }, headers=headers)
        body = check(f"POST /score user #{i+1}", r, 200)
        print(f"  seq={body['data']['sequence']}, score={body['data']['score']}, server={body['data']['current_server']}")

    # ---- 7. 对手得分 x3 ----
    print("\n=== 7. Score opponent x3 ===")
    for i in range(3):
        r = client.post(f"/api/v1/scoring/matches/{match_id}/score", json={
            "scorer": "opponent",
            "score_method": "serve_point",
        }, headers=headers)
        body = check(f"POST /score opp #{i+1}", r, 200)

    # ---- 8. 撤销 ----
    print("\n=== 8. Undo ===")
    r = client.post(f"/api/v1/scoring/matches/{match_id}/undo", headers=headers)
    body = check("POST /undo", r, 200)
    print(f"  seq={body['data']['sequence']}, score={body['data']['score']}")

    # ---- 9. 继续记分到 user 获胜 (left=5 after undo, need 6 more to reach 11) ----
    print("\n=== 9. Score to Win ===")
    for i in range(6):
        r = client.post(f"/api/v1/scoring/matches/{match_id}/score", json={
            "scorer": "user",
            "score_method": "rally_point",
        }, headers=headers)
        body = check(f"POST /score win #{i+1}", r, 200)

    # ---- 10. 结束比赛 ----
    print("\n=== 10. Finish ===")
    r = client.post(f"/api/v1/scoring/matches/{match_id}/finish", headers=headers)
    body = check("POST /finish", r, 200)
    print(f"  final_score={body['data']['final_score']}, is_win={body['data']['is_win']}")

    # ---- 11. 统计 ----
    print("\n=== 11. Statistics ===")
    r = client.get(f"/api/v1/scoring/matches/{match_id}/statistics", headers=headers)
    body = check("GET /statistics", r, 200)
    print(f"  match_id={body['data']['match_id']}, stats keys={list(body['data'].get('stats_data', {}).keys())[:5]}")

    # ---- 12. Abandon + Resume ----
    print("\n=== 12. Abandon + Resume ===")
    r = client.post("/api/v1/scoring/matches", json={
        "opponent_name": "许昕",
        "format": "bo3",
        "match_type": "training",
    }, headers=headers)
    body = check("POST /matches #2", r, 200)
    match2_id = body["data"]["match_id"]
    print(f"  match2_id={match2_id}")

    r = client.post(f"/api/v1/scoring/matches/{match2_id}/start", headers=headers)
    check("POST /start #2", r, 200)

    r = client.post(f"/api/v1/scoring/matches/{match2_id}/abandon", headers=headers)
    body = check("POST /abandon", r, 200)
    print(f"  status={body['data']['status']}")

    r = client.post(f"/api/v1/scoring/matches/{match2_id}/resume", headers=headers)
    body = check("POST /resume", r, 200)
    print(f"  status={body['data']['status']}")

    # ---- 13. Match-data: 快速录入 ----
    print("\n=== 13. Match-data Quick Record ===")
    r = client.post("/api/v1/match-data/records", json={
        "opponent_name": "马琳",
        "my_score": 3,
        "opponent_score": 1,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": "2026-10-21T10:00:00Z",
    }, headers=headers)
    body = check("POST /records (quick)", r, 200)
    record_id = body["data"]["id"]
    print(f"  record_id={record_id}, is_win={body['data']['is_win']}")

    # ---- 14. Match-data: 详细录入 ----
    print("\n=== 14. Match-data Detailed Record ===")
    r = client.post("/api/v1/match-data/records", json={
        "opponent_name": "王励勤",
        "my_score": 2,
        "opponent_score": 1,
        "format": "bo3",
        "match_type": "tournament",
        "match_date": "2026-10-21T14:00:00Z",
        "details": [
            {"sequence": 1, "scorer": "user", "score_method": "serve_point"},
            {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
            {"sequence": 3, "scorer": "user", "score_method": "opponent_error", "technique_action": "正手拉球"},
        ],
    }, headers=headers)
    body = check("POST /records (detailed)", r, 200)
    record2_id = body["data"]["id"]
    print(f"  record2_id={record2_id}")

    # ---- 15. Match-data: 列表 ----
    print("\n=== 15. Match-data List ===")
    r = client.get("/api/v1/match-data/records", headers=headers)
    body = check("GET /records (list)", r, 200)
    items = body["data"]["items"]
    print(f"  total={len(items)} records")

    # ---- 16. Match-data: 详情 ----
    print("\n=== 16. Match-data Detail ===")
    r = client.get(f"/api/v1/match-data/records/{record_id}", headers=headers)
    body = check("GET /records/{id}", r, 200)
    print(f"  opponent={body['data']['opponent_name']}, is_win={body['data']['is_win']}")

    # ---- 17. Match-data: 编辑 ----
    print("\n=== 17. Match-data Edit ===")
    r = client.patch(f"/api/v1/match-data/records/{record_id}", json={
        "notes": "E2E updated notes",
    }, headers=headers)
    body = check("PATCH /records/{id}", r, 200)
    print(f"  message={body['message']}")

    # ---- 18. 无认证检查 ----
    print("\n=== 18. Auth Check ===")
    r = client.get("/api/v1/scoring/matches")
    check("GET /matches (no auth → 401)", r, 401)

    # ---- Summary ----
    print(f"\n{'='*60}")
    print(f"E2E Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    return failed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(1 if result > 0 else 0)
