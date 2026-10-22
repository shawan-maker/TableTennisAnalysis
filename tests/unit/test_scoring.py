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
