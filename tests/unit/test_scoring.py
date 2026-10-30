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
async def test_undo_match_not_in_progress_409(client, auth_headers):
    """R12-SC-9: 比赛未在进行中（未 start，pending）时撤销 → 409（ERR_MATCH_STATE_CONFLICT 40910）"""
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "对手SC9"},
    )
    match_id = resp1.json()["data"]["match_id"]

    # 不调用 /start — 比赛仍为 pending → undo → 409
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=auth_headers
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == 40910  # ERR_MATCH_STATE_CONFLICT


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


# =====================================================================
# R13-SC-1 回归：多局赛制推进（bo3 局分累计 + 达赛制自动结束 + 跨局保护）
# =====================================================================

@pytest.mark.asyncio
async def test_multi_game_progression_bo3_auto_finish(client, auth_headers, auth_user, monkeypatch):
    """R12-SC-1: bo3（3 局 2 胜）— 连赢 2 局后全场自动结束，
    is_win/final_score 按局分判定，ScoreRecord 的 game_number 归属正确"""
    # R13-AIP-1/ND-1: 比赛结束级联投递断言 — spy 化 bust_cache_task
    # （eager 模式下任务体在新线程 asyncio.run 执行，与主循环连接池跨循环
    #   冲突；投递参数契约由本断言锁定，任务体语义由 test_dashboard 直调验证）
    bust_calls: list = []

    class _BustSpy:
        @staticmethod
        def delay(*args, **kwargs):
            bust_calls.append((args, kwargs))

    monkeypatch.setattr("app.tasks.dashboard.bust_cache_task", _BustSpy)

    # 创建 bo3 比赛
    resp = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "多局对手", "format": "bo3"},
    )
    assert resp.status_code == 200
    match_id = resp.json()["data"]["match_id"]

    resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )
    assert resp.status_code == 200

    # 第 1 局：user 连得 11 分（11:0 ≥ target_score 11 且净胜 ≥ 2 → 局结束）
    last = None
    for _ in range(11):
        last = await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            headers=auth_headers,
            json={"scorer": "user", "score_method": "serve_point"},
        )
        assert last.status_code == 200
    d1 = last.json()["data"]
    # 第 1 局结束：进入第 2 局，比分清零，未达 2 胜 → 不结束
    assert d1["match_finished"] is False
    assert d1["match_status"] == "in_progress"
    assert d1["game_number"] == 2, "第 1 局结束后 current_game 应递增到 2"

    # 第 2 局：user 再连得 11 分 → 局分 2:0 达 bo3 要求 → 全场自动结束
    for _ in range(11):
        last = await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            headers=auth_headers,
            json={"scorer": "user", "score_method": "rally_point"},
        )
        assert last.status_code == 200
    d2 = last.json()["data"]
    assert d2["match_finished"] is True, "bo3 赢 2 局后全场应自动结束"
    assert d2["match_status"] == "finished"

    # 终局校验：is_win 按局分（games_won_user=2 > games_won_opp=0）
    detail = await client.get(
        f"/api/v1/scoring/matches/{match_id}", headers=auth_headers
    )
    assert detail.status_code == 200
    dd = detail.json()["data"]
    assert dd["status"] == "finished"
    assert dd["is_win"] is True, "局分 2:0 的胜者 is_win 应为 True"
    assert dd["final_score"] == "2:0", "final_score 应按局分判定（2:0）"

    # 级联投递断言：比赛自动结束 -> dashboard.bust_cache(user_id, "match_end") 恰好一次
    assert len(bust_calls) == 1, f"比赛结束应投递一次看板缓存失效，实际 {len(bust_calls)} 次"
    assert bust_calls[0][0] == (auth_user["user_id"], "match_end"), (
        f"投递参数错误：{bust_calls[0][0]}"
    )


@pytest.mark.asyncio
async def test_multi_game_cross_game_undo_protection(client, auth_headers):
    """R12-SC-1: 跨局撤销保护 — 撤销已结束上一局的致胜球返回 400"""
    from app.models.match import Match

    # 创建 bo3 比赛（db_session 用于直查 Match 的局分/局号）
    resp = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "跨局对手", "format": "bo3"},
    )
    match_id = resp.json()["data"]["match_id"]
    await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers
    )

    # 第 1 局：user 连得 11 分（最后一球 seq=11 是致胜球，game_number=1）
    for _ in range(11):
        r = await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            headers=auth_headers,
            json={"scorer": "user", "score_method": "serve_point"},
        )
        assert r.status_code == 200
    # 此时 current_game=2（局分 user 1:0），最近一条记录 game_number=1

    # 第 2 层防护验证：undo 最近一球（game_number=1 < current_game=2）→ 400
    undo_resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=auth_headers
    )
    assert undo_resp.status_code == 400
    assert "不可撤销" in undo_resp.json()["message"]
