"""
tests/unit/test_user.py — user 模块单元测试

依据：切片 02-user/backend.md §2 测试先行
覆盖：档案获取/更新、积分更新+历史、乒乓大数据、用户注销、数据导出
"""

import pytest

from app.models.user import ExportTask


# =================================================================
# 个人档案（已有端点回归测试）
# =================================================================

@pytest.mark.asyncio
async def test_get_profile(client, auth_headers, test_user):
    """获取个人档案"""
    resp = await client.get("/api/v1/users/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == test_user.id
    assert data["nickname"] == "测试用户"
    assert "profile_completeness" in data


@pytest.mark.asyncio
async def test_update_profile(client, auth_headers):
    """更新个人档案"""
    resp = await client.patch(
        "/api/v1/users/profile",
        headers=auth_headers,
        json={
            "playing_style": "loop",
            "self_assessed_level": "intermediate",
            "equipment_config": {"blade": {"brand": "蝴蝶", "model": "Viscaria"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "profile_completeness" in data
    assert "playing_style" in data["updated_fields"]


# =================================================================
# 积分历史（已有端点回归测试）
# =================================================================

@pytest.mark.asyncio
async def test_update_rating(client, auth_headers):
    """更新积分成功，旧积分自动写入历史记录"""
    resp = await client.patch(
        "/api/v1/users/rating",
        headers=auth_headers,
        json={"rating": 1550, "source": "manual"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new_rating"] == 1550
    assert "history_id" in data


@pytest.mark.asyncio
async def test_rating_history_pagination(client, auth_headers):
    """积分历史记录支持分页查询"""
    # 先设置一个初始积分，确保后续更新都能产生历史记录
    for rating in [1500, 1520, 1550]:
        await client.patch(
            "/api/v1/users/rating",
            headers=auth_headers,
            json={"rating": rating, "source": "manual"},
        )

    resp = await client.get(
        "/api/v1/users/rating-history?page=1&page_size=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 首次更新无旧积分不产生历史记录，故 3 次更新产生 2 条历史
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


# =================================================================
# 乒乓大数据（新增端点）
# =================================================================

@pytest.mark.asyncio
async def test_get_big_data(client, auth_headers):
    """乒乓大数据端点正常响应"""
    resp = await client.get("/api/v1/users/big-data", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_matches" in data
    assert "win_rate" in data
    assert "win_streak" in data
    assert "indirect_wins" in data
    assert "total_opponents" in data


# =================================================================
# 用户注销（新增端点）
# =================================================================

@pytest.mark.asyncio
async def test_delete_account_success(client, auth_headers):
    """用户注销成功，返回 72h 冷静期信息"""
    resp = await client.request(
        "DELETE",
        "/api/v1/users/account",
        headers=auth_headers,
        json={"reason": "不再使用", "confirmation": "DELETE_ACCOUNT_CONFIRM"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "scheduled_deletion_at" in data
    assert "can_cancel_before" in data


@pytest.mark.asyncio
async def test_delete_account_wrong_confirmation(client, auth_headers):
    """confirmation 不匹配返回 422"""
    resp = await client.request(
        "DELETE",
        "/api/v1/users/account",
        headers=auth_headers,
        json={"reason": "不再使用", "confirmation": "WRONG"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_account_deletion_cooldown(client, auth_headers):
    """重复提交注销返回 409"""
    # 第一次提交
    resp1 = await client.request(
        "DELETE",
        "/api/v1/users/account",
        headers=auth_headers,
        json={"reason": "不再使用", "confirmation": "DELETE_ACCOUNT_CONFIRM"},
    )
    assert resp1.status_code == 200

    # 第二次提交 → 409
    resp2 = await client.request(
        "DELETE",
        "/api/v1/users/account",
        headers=auth_headers,
        json={"reason": "不再使用", "confirmation": "DELETE_ACCOUNT_CONFIRM"},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_cancel_deletion_success(client, auth_headers):
    """撤销注销申请成功"""
    # 先提交注销
    await client.request(
        "DELETE",
        "/api/v1/users/account",
        headers=auth_headers,
        json={"reason": "不再使用", "confirmation": "DELETE_ACCOUNT_CONFIRM"},
    )

    # 撤销注销
    resp = await client.post(
        "/api/v1/users/account/cancel-deletion",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_cancel_deletion_without_pending(client, auth_headers):
    """无待执行的注销申请时返回 409"""
    resp = await client.post(
        "/api/v1/users/account/cancel-deletion",
        headers=auth_headers,
    )
    assert resp.status_code == 409


# =================================================================
# 数据导出（新增端点）
# =================================================================

@pytest.mark.asyncio
async def test_export_data_success(client, auth_headers):
    """发起数据导出成功，返回 task_id"""
    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["task_id"].startswith("export_")


@pytest.mark.asyncio
async def test_export_data_monthly_limit(client, auth_headers):
    """同月内重复导出返回 429"""
    # 第一次导出
    resp1 = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp1.status_code == 200

    # 第二次导出 → 429
    resp2 = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp2.status_code == 429


@pytest.mark.asyncio
async def test_get_export_status_not_found(client, auth_headers):
    """查询不存在的导出任务返回 404"""
    resp = await client.get(
        "/api/v1/users/export-data/nonexistent_task",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_export_status_processing(client, auth_headers):
    """查询处理中的导出任务返回 409"""
    # 先创建导出任务
    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    # 查询状态 → 409（pending 状态）
    resp2 = await client.get(
        f"/api/v1/users/export-data/{task_id}",
        headers=auth_headers,
    )
    assert resp2.status_code == 409


# =================================================================
# 未认证测试
# =================================================================

@pytest.mark.asyncio
async def test_big_data_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.get("/api/v1/users/big-data")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_account_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.delete("/api/v1/users/account")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_data_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.post("/api/v1/users/export-data")
    assert resp.status_code == 401
