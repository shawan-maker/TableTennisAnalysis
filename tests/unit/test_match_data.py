"""
tests/unit/test_match_data.py — 比赛数据模块单元测试

依据：切片 05-match_data/backend.md §8 测试先行
覆盖：快速录入/详细录入/列表/详情/编辑 + 比分验证
"""

from datetime import datetime, timezone

import pytest


# =================================================================
# 创建比赛记录
# =================================================================

@pytest.mark.asyncio
async def test_quick_create_success(client, auth_headers):
    """快速录入 — bo5 3:1 胜"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手0",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_type": "friendly",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "id" in data
    assert data["is_win"] is True


@pytest.mark.asyncio
async def test_quick_create_lose(client, auth_headers):
    """快速录入 — bo5 1:3 负"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手1",
            "my_score": 1,
            "opponent_score": 3,
            "format": "bo5",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_win"] is False


@pytest.mark.asyncio
async def test_detailed_create_success(client, auth_headers):
    """详细录入 — custom 11:8 + 得分明细"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手2",
            "my_score": 11,
            "opponent_score": 8,
            "format": "custom",
            "details": [
                {"sequence": 1, "scorer": "user", "score_method": "serve_point"},
                {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
                {"sequence": 3, "scorer": "user", "score_method": "serve_point"},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_win"] is True


@pytest.mark.asyncio
async def test_create_invalid_score_bo5(client, auth_headers):
    """比分不符合赛制规则 — bo5 5:3 返回 422"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手3",
            "my_score": 5,
            "opponent_score": 3,
            "format": "bo5",
        },
    )
    assert resp.status_code == 422
    assert "赛制规则" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_equal_scores(client, auth_headers):
    """比分相同返回 422"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手4",
            "my_score": 3,
            "opponent_score": 3,
            "format": "bo5",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_future_date(client, auth_headers):
    """比赛日期在未来返回 422"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手5",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_date": "2099-12-31T00:00:00Z",
        },
    )
    assert resp.status_code == 422


# =================================================================
# 列表
# =================================================================

@pytest.mark.asyncio
async def test_list_records(client, auth_headers):
    """比赛记录列表"""
    # 创建几条记录
    for i in range(3):
        await client.post(
            "/api/v1/match-data/records",
            headers=auth_headers,
            json={
                "opponent_name": f"对手{i}",
                "my_score": 3,
                "opponent_score": 1,
                "format": "bo5",
            },
        )

    resp = await client.get(
        "/api/v1/match-data/records", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_list_records_filter_win(client, auth_headers):
    """列表过滤胜场"""
    await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "win_opp", "my_score": 3, "opponent_score": 1, "format": "bo5"},
    )
    await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "lose_opp", "my_score": 1, "opponent_score": 3, "format": "bo5"},
    )

    resp = await client.get(
        "/api/v1/match-data/records?result=win", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(item["is_win"] is True for item in data["items"])


# =================================================================
# 详情
# =================================================================

@pytest.mark.asyncio
async def test_get_detail_with_details(client, auth_headers):
    """详情含得分明细"""
    resp1 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "对手详情",
            "my_score": 11,
            "opponent_score": 8,
            "format": "custom",
            "details": [
                {"sequence": 1, "scorer": "user", "score_method": "serve_point"},
                {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"},
            ],
        },
    )
    record_id = resp1.json()["data"]["id"]

    resp2 = await client.get(
        f"/api/v1/match-data/records/{record_id}", headers=auth_headers
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["id"] == record_id
    assert data["is_detailed"] is True
    assert len(data["details"]) == 2


@pytest.mark.asyncio
async def test_get_detail_not_found(client, auth_headers):
    """记录不存在返回 404"""
    resp = await client.get(
        "/api/v1/match-data/records/99999", headers=auth_headers
    )
    assert resp.status_code == 404


# =================================================================
# 编辑
# =================================================================

@pytest.mark.asyncio
async def test_update_record_opponent_name(client, auth_headers):
    """编辑对手名"""
    resp1 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "原名", "my_score": 3, "opponent_score": 1, "format": "bo5"},
    )
    record_id = resp1.json()["data"]["id"]

    resp2 = await client.patch(
        f"/api/v1/match-data/records/{record_id}",
        headers=auth_headers,
        json={"opponent_name": "新名"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["id"] == record_id


@pytest.mark.asyncio
async def test_update_record_score_recalc_is_win(client, auth_headers):
    """修改比分后 is_win 自动重算"""
    resp1 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "对手", "my_score": 3, "opponent_score": 1, "format": "bo5"},
    )
    record_id = resp1.json()["data"]["id"]

    # 改成 1:3
    resp2 = await client.patch(
        f"/api/v1/match-data/records/{record_id}",
        headers=auth_headers,
        json={"my_score": 1, "opponent_score": 3},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["is_win"] is False


@pytest.mark.asyncio
async def test_update_record_not_found(client, auth_headers):
    """编辑不存在的记录返回 404"""
    resp = await client.patch(
        "/api/v1/match-data/records/99999",
        headers=auth_headers,
        json={"opponent_name": "test"},
    )
    assert resp.status_code == 404


# =================================================================
# 认证
# =================================================================

@pytest.mark.asyncio
async def test_match_data_unauthorized(client):
    """未认证返回 401"""
    resp = await client.get("/api/v1/match-data/records")
    assert resp.status_code == 401
