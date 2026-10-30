"""
tests/unit/test_rate_limiting.py — slowapi API 限流层专项测试

R12-Gam-13: 限流装饰器顺序修复（router 在上 / limiter 在下）后的对照测试。

背景：全 app 95 处 @limiter.limit 原置于 @router.<method> 上方 — 路由表注册的
是原始未包装函数，limit 检查从不执行（限流为死代码，从未生效）。批量交换后
route.endpoint 为 slowapi 包装函数（带 __wrapped__），限流真实生效。

测试策略：conftest 默认 limiter.enabled=False（防 429 污染常规断言），
本文件 autouse fixture 临时启用（monkeypatch 自动恢复）：
1. wiring 元测试：95 个限流端点全部 __wrapped__（防装饰器顺序回退）
2. 超限 → slowapi 429（{"error": "Rate limit exceeded: ..."}，
   send-sms 1/minute；用不同手机号证明 429 来自限流层而非服务层 60s 防刷）
3. 未超限 → 业务错误不被遮蔽（score 未开始 409 可达）
4. per-IP 计数隔离：key_func=get_remote_address — 不同 remote address 独立计数
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.limiter import limiter


@pytest.fixture(autouse=True)
def _enable_limiter(monkeypatch):
    """本文件临时启用 slowapi 限流（conftest 默认禁用，结束后自动恢复）

    R13-RL-Test-1：limiter storage 为共享远程 Redis（limits 库键前缀 LIMITS:*），
    计数键 TTL = 限流窗口（checkin 1/day → 24h）→ 跨测试/跨运行残留使本文件非幂等
    （第二次全量回归 resp1 即 429；实证残留键 LIMITS:LIMITER/user:1//.../checkin/1/1/day
    value=3、TTL≈22h）。每测试前 limiter.reset() —— limits 库 Lua 脚本仅按
    LIMITS:* 前缀分块删除，不触碰其他业务键，保证每个测试从零计数开始。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    yield


# =============================================================================
# 1. 装饰器顺序 wiring 元测试（回归防护）
# =============================================================================

def test_limited_endpoints_wiring():
    """95 个挂 @limiter.limit 的端点 route.endpoint 必须带 __wrapped__

    装饰器若错放 @router 上方（历史缺陷），路由表注册原始函数 → 限流死代码。
    """
    from app.main import app

    wrapped = [
        (route.path, route.endpoint.__name__)
        for route in app.routes
        if getattr(route, "endpoint", None) is not None
        and hasattr(route.endpoint, "__wrapped__")
    ]
    # 修复后 95 条限流路由全部生效（修复前为 0）
    assert len(wrapped) >= 95

    # 抽查各限流档位代表端点（修复前这些名字全部不在包装集中）
    names = {name for _, name in wrapped}
    for expected in [
        "wechat_login", "send_sms", "phone_login", "admin_login",  # 认证档
        "score", "undo",                                           # 记分
        "submit_feedback", "create_share", "create_task",          # 业务档
        "checkin", "export_data",                                  # 低频档
        "get_landing_heatmap", "list_notifications", "mark_read",  # 常规档
    ]:
        assert expected in names, f"端点 {expected} 未被 slowapi 包装（装饰器顺序回退？）"


# =============================================================================
# 2. 超限 → slowapi 429
# =============================================================================

@pytest.mark.asyncio
async def test_send_sms_over_limit_returns_slowapi_429(client):
    """send-sms 1/minute：第 2 次请求 → slowapi 429（先于服务层执行）

    换手机号排除服务层 60s 防刷（AppException 429）：若 429 来自服务层，
    换号后应返回 200；来自 slowapi 层则与手机号无关，仍 429。
    """
    # 第 1 次（新号）→ 通过限流检查 + 通过服务层防刷 → 200
    resp1 = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13800000001"},
    )
    assert resp1.status_code == 200

    # 第 2 次（换新号绕开服务层防刷）→ slowapi 1/minute 超限 → 429
    resp2 = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13800000002"},
    )
    assert resp2.status_code == 429
    # slowapi 处理器返回 {"error": "Rate limit exceeded: ..."}（非业务包装格式）
    assert resp2.json()["error"].startswith("Rate limit exceeded")


# =============================================================================
# 3. 未超限 → 业务错误不被遮蔽
# =============================================================================

@pytest.mark.asyncio
async def test_business_409_not_masked_below_limit(client, auth_headers):
    """限流启用 + 未超限 → 业务 409 照常可达（不被 429 遮蔽）

    R12-Gam-13 关注点："429 遮蔽业务错误"的前提是限流生效。修复后本测试证明：
    限流真实生效的场景下，未超限的业务错误（score 未开始 409）正常返回。
    """
    resp1 = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "限流对照对手"},
    )
    assert resp1.status_code == 200
    match_id = resp1.json()["data"]["match_id"]

    # 单次请求远低于 score 端点限流 → 业务 409 原样返回
    resp2 = await client.post(
        f"/api/v1/scoring/matches/{match_id}/score",
        headers=auth_headers,
        json={"scorer": "user", "score_method": "serve_point"},
    )
    assert resp2.status_code == 409


# =============================================================================
# 4. per-IP 计数隔离
# =============================================================================

@pytest.mark.asyncio
async def test_rate_limit_per_ip_isolation():
    """key_func=get_remote_address → 不同 remote address 独立计数

    A IP 第 1 次 → 200；B IP 第 1 次 → 200（不受 A 消耗影响）；
    A IP 第 2 次 → 429（A 自身 1/minute 耗尽）。
    """
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.10", 11111)),
        base_url="http://test-a",
    ) as client_a:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.20", 22222)),
            base_url="http://test-b",
        ) as client_b:
            resp_a1 = await client_a.post(
                "/api/v1/auth/send-sms", json={"phone": "13800000011"},
            )
            assert resp_a1.status_code == 200

            # B 独立计数 → 不被 A 的消耗阻挡
            resp_b1 = await client_b.post(
                "/api/v1/auth/send-sms", json={"phone": "13800000012"},
            )
            assert resp_b1.status_code == 200

            # A 第 2 次 → A 自身超限
            resp_a2 = await client_a.post(
                "/api/v1/auth/send-sms", json={"phone": "13800000013"},
            )
            assert resp_a2.status_code == 429


# =============================================================================
# 5. checkin 1/day 按用户限流（Gam-13 遮蔽语义实证）
# =============================================================================

@pytest.mark.asyncio
async def test_checkin_daily_limit_returns_slowapi_429(client, auth_headers):
    """checkin 1/day（key_func 按用户）：第 2 次 → slowapi 429，先于业务同日 409

    Gam-13"429 遮蔽业务 409"实证：限流生效后，同用户当日第 2 次打卡被限流层
    拦截（429），业务层同日 409 不可达（该路径由 test_gamification.
    test_checkin_duplicate 在 limiter 禁用下验证）— 两层防护均为设计意图。
    """
    resp1 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp1.status_code == 200

    resp2 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp2.status_code == 429
    assert resp2.json()["error"].startswith("Rate limit exceeded")
