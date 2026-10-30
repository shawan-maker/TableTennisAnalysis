"""
tests/unit/test_user.py — user 模块单元测试

依据：切片 02-user/backend.md §2 测试先行
覆盖：档案获取/更新、积分更新+历史、乒乓大数据、用户注销、数据导出
"""

import pytest

from app.core.security import create_access_token, generate_jti
from app.models.user import ExportTask, User


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
    assert "profile_completeness" in data["profile"]


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

class _ExportDispatchSpy:
    """记录 export_user_data.delay 投递调用

    避免 eager 内联在线程池新事件循环中执行任务体（与主循环共用
    asyncpg 连接池 → 跨 loop "Future attached to a different loop"）。
    生产 worker 为独立进程/循环，无此问题；测试用 spy 验证投递链路 +
    直调异步实现（等价路径）验证任务体。
    """

    def __init__(self):
        self.calls = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.fixture
def export_spy(monkeypatch):
    spy = _ExportDispatchSpy()
    monkeypatch.setattr("app.tasks.user.export_user_data", spy)
    return spy


@pytest.mark.asyncio
async def test_export_data_success(client, auth_headers, auth_user, export_spy):
    """发起数据导出成功 + R12-User-2 投递链路接通（原 delay TODO 断链）"""
    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["task_id"].startswith("export_")

    # delay 投递已接通，参数正确（user_id + task_id）
    assert len(export_spy.calls) == 1
    (user_id, task_id), _ = export_spy.calls[0]
    assert user_id == auth_user["user_id"]
    assert task_id == data["task_id"]


@pytest.mark.asyncio
async def test_export_data_monthly_limit(client, auth_headers, export_spy):
    """同月内重复导出返回 429"""
    # 第一次导出
    resp1 = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp1.status_code == 200

    # 第二次导出 → 429（业务月度限流，不再投递）
    resp2 = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp2.status_code == 429
    assert len(export_spy.calls) == 1


@pytest.mark.asyncio
async def test_get_export_status_not_found(client, auth_headers):
    """查询不存在的导出任务返回 404"""
    resp = await client.get(
        "/api/v1/users/export-data/nonexistent_task",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_export_status_pending_409(client, auth_headers, export_spy):
    """任务已投递（worker 处理前）查询 → 409 处理中"""
    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    resp2 = await client.get(
        f"/api/v1/users/export-data/{task_id}",
        headers=auth_headers,
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_export_task_impl_completes(client, auth_headers, auth_user, export_spy):
    """导出任务体直调（主循环等价路径）：pending → completed + download_url + 7 天 expire_at

    生产 worker 经 _run_async 执行；测试直调异步实现验证任务体语义。
    """
    from app.tasks.user import _export_user_data_async

    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    await _export_user_data_async(auth_user["user_id"], task_id)

    resp2 = await client.get(
        f"/api/v1/users/export-data/{task_id}",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["task_id"] == task_id
    assert data["status"] == "completed"
    assert data["download_url"].startswith("https://")
    assert data["expire_at"] is not None


@pytest.mark.asyncio
async def test_get_export_status_cross_user_404(client, auth_headers, db_session, export_spy):
    """R12-User-5: 其他用户查询我的导出任务 → 404（资源隔离，task_id+user_id 双条件）"""
    resp = await client.post(
        "/api/v1/users/export-data",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    # 用户 B 尝试查询用户 A 的导出任务
    user_b = User(openid="user5_export_iso_b", nickname="用户B", status="active")
    db_session.add(user_b)
    await db_session.commit()
    token_b = create_access_token({"sub": str(user_b.id), "jti": generate_jti()})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp2 = await client.get(
        f"/api/v1/users/export-data/{task_id}",
        headers=headers_b,
    )
    assert resp2.status_code == 404
    assert resp2.json()["code"] == 40400  # ERR_NOT_FOUND

    # 对照：属主查询可达（pending → 409，非 404）
    resp3 = await client.get(
        f"/api/v1/users/export-data/{task_id}",
        headers=auth_headers,
    )
    assert resp3.status_code == 409


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
