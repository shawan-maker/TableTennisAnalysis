"""
tests/unit/test_scoring.py — 记分牌模块单元测试

依据：切片 04-scoring/backend.md §8 测试先行
覆盖：比赛创建/列表/详情/记分/撤销/开始/结束/放弃/恢复/统计
"""

import pytest


# =================================================================
# 比赛创建
# =================================================================

@pytest.mark.asyncio
async def test_create_match(client, auth_headers):
    """创建比赛 — 返回 match_id + status=setup"""
    resp = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={
            "opponent_name": "张某",
            "opponent_rating": 1480,
            "format": "bo5",
            "match_type": "friendly",
            "target_score": 11,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "match_id" in data
    assert data["status"] == "setup"
    assert data["current_server"] == "user"


@pytest.mark.asyncio
async def test_create_match_default_values(client, auth_headers):
    """创建比赛 — 默认值 bo5/friendly/11"""
    resp = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_match_invalid_format(client, auth_headers):
    """赛制不合法返回 422"""
    resp = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手", "format": "invalid"},
    )
    assert resp.status_code == 422


# =================================================================
# 比赛列表
# =================================================================

@pytest.mark.asyncio
async def test_list_matches(client, auth_headers):
    """比赛列表 — 分页返回"""
    # 先创建一场比赛
    await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手A"},
    )
    resp = await client.get("/api/v1/scoring/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


# =================================================================
# 比赛详情
# =================================================================

@pytest.mark.asyncio
async def test_get_match_detail(client, auth_headers):
    """比赛详情"""
    # 创建
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手B"},
    )
    match_id = resp1.json()["data"]["match_id"]

    resp2 = await client.get(
        f"/api/v1/scoring/matches/{match_id}", headers=auth_headers
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["id"] == match_id
    assert data["opponent_name"] == "对手B"
    assert "score_sequence" in data


@pytest.mark.asyncio
async def test_get_match_not_found(client, auth_headers):
    """比赛不存在返回 404"""
    resp = await client.get(
        "/api/v1/scoring/matches/99999", headers=auth_headers
    )
    assert resp.status_code == 404


# =================================================================
# 状态机：开始/记分/撤销/结束
# =================================================================

@pytest.mark.asyncio
async def test_start_and_score(client, auth_headers):
    """开始比赛 + 记分"""
    # 创建
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手C"},
    )
    match_id = resp1.json()["data"]["match_id"]

    # 开始
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["status"] == "in_progress"

    # 记分
    resp3 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    assert resp3.status_code == 200
    data = resp3.json()["data"]
    assert data["sequence"] == 1
    assert data["score"] == "1:0"
    assert data["current_server"] in ["user", "opponent"]


@pytest.mark.asyncio
async def test_score_without_start(client, auth_headers):
    """未开始的比赛记分返回 409"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手D"},
    )
    match_id = resp1.json()["data"]["match_id"]

    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_undo(client, auth_headers):
    """撤销最近一球"""
    # 创建 + 开始 + 记分
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手E"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "opponent", "score_method": "rally_point"},
    )

    # 撤销
    resp3 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=auth_headers
    )
    assert resp3.status_code == 200
    data = resp3.json()["data"]
    assert data["type"] == "undo"
    assert data["sequence"] == 1  # 2 -> 1
    assert data["score"] == "1:0"


@pytest.mark.asyncio
async def test_undo_no_records(client, auth_headers):
    """没有可撤销的记录返回 400"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手F"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )

    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=auth_headers
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_finish_match(client, auth_headers):
    """结束比赛 + 生成统计"""
    # 创建 + 开始 + 记分
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手G"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    # 记 3 个球
    for _ in range(3):
        await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            headers=auth_headers,
            json={"scorer": "user", "score_method": "serve_point"},
        )

    # 结束
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=auth_headers
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["match_id"] == match_id
    assert data["final_score"] == "3:0"
    assert data["is_win"] is True
    assert "statistic_id" in data


@pytest.mark.asyncio
async def test_get_statistics(client, auth_headers):
    """获取比赛统计"""
    # 创建 + 开始 + 记分 + 结束
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手H"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "opponent", "score_method": "rally_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=auth_headers
    )

    resp2 = await client.get(
        f"/api/v1/scoring/matches/{match_id}/statistics", headers=auth_headers
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["match_id"] == match_id
    assert "stats_data" in data
    assert data["stats_data"]["total_points"] == 2
    assert data["stats_data"]["score_distribution"]["serve_point"] == 1
    assert data["stats_data"]["score_distribution"]["rally_point"] == 1


# =================================================================
# 状态机：放弃/恢复
# =================================================================

@pytest.mark.asyncio
async def test_abandon_and_resume(client, auth_headers):
    """放弃比赛 + 恢复"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手I"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )

    # 放弃
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/abandon", headers=auth_headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["status"] == "abandoned"

    # 恢复
    resp3 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/resume", headers=auth_headers
    )
    assert resp3.status_code == 200
    assert resp3.json()["data"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_abandon_not_in_progress(client, auth_headers):
    """非进行中的比赛不能放弃"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手J"},
    )
    match_id = resp1.json()["data"]["match_id"]

    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/abandon", headers=auth_headers
    )
    assert resp2.status_code == 400


# =================================================================
# 认证
# =================================================================

@pytest.mark.asyncio
async def test_scoring_unauthorized(client):
    """未认证返回 401"""
    resp = await client.get("/api/v1/scoring/matches")
    assert resp.status_code == 401


# =================================================================
# 边界场景补充
# =================================================================

@pytest.mark.asyncio
async def test_finish_without_scores(client, auth_headers):
    """无记分直接结束比赛 — 0:0"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_无分结束"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )

    # 直接结束
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=auth_headers
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["final_score"] == "0:0"
    assert data["is_win"] is False


@pytest.mark.asyncio
async def test_list_matches_filter_by_status(client, auth_headers):
    """按状态过滤比赛列表"""
    # 创建 setup 状态的比赛
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "setup_match"},
    )
    # 创建 in_progress 比赛
    resp2 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "in_progress_match"},
    )
    mid2 = resp2.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{mid2}/start", headers=auth_headers
    )
    # 创建 finished 比赛
    resp3 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "finished_match"},
    )
    mid3 = resp3.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{mid3}/start", headers=auth_headers
    )
    await client.post(
        f"/api/v1/scoring/matches/{mid3}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{mid3}/finish", headers=auth_headers
    )

    # 过滤 setup
    resp = await client.get(
        "/api/v1/scoring/matches?status=setup", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["status"] == "setup" for i in items)

    # 过滤 in_progress
    resp = await client.get(
        "/api/v1/scoring/matches?status=in_progress", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["status"] == "in_progress" for i in items)

    # 过滤 finished
    resp = await client.get(
        "/api/v1/scoring/matches?status=finished", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["status"] == "finished" for i in items)


@pytest.mark.asyncio
async def test_undo_with_expected_seq_mismatch(client, auth_headers):
    """乐观并发：expected_seq 不匹配返回 409"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_并发"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    # 记 2 分
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "rally_point"},
    )

    # 撤销但 expected_seq=1（实际 max_seq=2）
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo",
        headers=auth_headers,
        json={"expected_seq": 1},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_resume_expired(client, auth_headers, db_session):
    """放弃超过 24h → 恢复返回 400"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from app.models.match import Match

    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_过期"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/abandon", headers=auth_headers
    )

    # 手动设置 abandoned_at 为 25h 前
    expired = datetime.now(timezone.utc) - timedelta(hours=25)
    await db_session.execute(
        update(Match).where(Match.id == match_id).values(abandoned_at=expired)
    )
    await db_session.commit()

    # 恢复 → 400
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/resume", headers=auth_headers
    )
    assert resp2.status_code == 400
    assert "24h" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_start_already_started(client, auth_headers):
    """重复开始比赛 → 400"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_重复开始"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )

    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_finish_already_finished(client, auth_headers):
    """重复结束比赛 → 409"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_重复结束"},
    )
    match_id = resp1.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=auth_headers
    )

    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/finish", headers=auth_headers
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_resume_not_abandoned(client, auth_headers):
    """恢复非放弃状态的比赛 → 400"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手_非放弃恢复"},
    )
    match_id = resp1.json()["data"]["match_id"]
    # setup 状态恢复 → 400
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/resume", headers=auth_headers
    )
    assert resp2.status_code == 400
