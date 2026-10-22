"""
app/core/response.py — 统一响应格式包装

架构约束：API §1.1 统一响应格式
规范：所有成功响应通过 success() 包装，错误通过 AppException 抛出
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success(
    data: Any = None,
    message: str = "success",
    status_code: int = 200,
) -> JSONResponse:
    """
    成功响应包装器 — 返回统一 JSON 格式。

    使用方式：
        return success(data=user_data, message="登录成功")
        return success(data=paginated_data)
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "code": 200,
            "message": message,
            "data": jsonable_encoder(data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def error(
    message: str,
    status_code: int = 400,
    data: Any = None,
    code: Optional[int] = None,
) -> JSONResponse:
    """
    错误响应包装器 — 仅用于特殊场景（如微信支付回调特殊响应格式）。
    通常业务错误应通过 raise AppException(...) 抛出。
    """
    if code is None:
        code = status_code * 100

    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "data": jsonable_encoder(data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
