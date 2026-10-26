"""
app/core/middleware.py — 请求级中间件

架构约束：§12.8 可观测性 / 切片 13-infrastructure/logging.md
功能：request_id 中间件 — 从 X-Request-ID header 或 uuid4()[:8] 生成 request_id，
     设置到 request_id_var（供日志关联），并回写到响应头 X-Request-ID。

实现为纯 ASGI 中间件（非 BaseHTTPMiddleware），对 WebSocket 请求直接透传，
     避免 BaseHTTPMiddleware 对 WS 的已知干扰。
"""

import uuid
from typing import Awaitable, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import request_id_var


class RequestIDMiddleware:
    """纯 ASGI 中间件 — 为每个 HTTP 请求注入 request_id。

    - HTTP 请求：从 X-Request-ID header 提取，缺失则生成 uuid4()[:8]；
      设置到 request_id_var；响应头回写 X-Request-ID。
    - WebSocket 请求：直接透传，不处理（WS 端点自行管理）。
    """

    HEADER_NAME = "x-request-id"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send,
    ) -> None:
        if scope["type"] != "http":
            # WebSocket 等非 HTTP 请求直接透传
            await self.app(scope, receive, send)
            return

        # 从请求头提取 request_id（缺失则生成）
        request_id = ""
        for name, value in scope.get("headers", []):
            if name == self.HEADER_NAME.encode("latin-1"):
                request_id = value.decode("latin-1")
                break
        if not request_id:
            request_id = uuid.uuid4().hex[:8]

        # 设置到 ContextVar（供日志/structlog processor 读取）
        token = request_id_var.set(request_id)

        # 响应头回写 X-Request-ID
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (self.HEADER_NAME.encode("latin-1"),
                     request_id.encode("latin-1"))
                )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)
