"""
app/core/exceptions.py — 统一异常处理 + 错误码定义

架构约束：§5.7 / §12.4 统一错误处理
依据：API §1.7 通用错误码 + §1.8 业务错误码
规范：全部业务错误使用 raise AppException(...)，禁止 HTTPException
"""

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """
    统一业务异常 — 所有业务错误必须通过此类抛出。

    使用方式：
        raise AppException("比赛不存在", 404, code=40411)
        raise AppException("验证码错误或已过期", 400, code=40000)

    中间件统一捕获并转换为标准 JSON 响应：
        {"code": 40411, "message": "比赛不存在", "data": null, "timestamp": "..."}
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        *,
        code: Optional[int] = None,
        detail: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        # 如果未指定 code，使用 HTTP 状态码 * 100 作为通用 code
        self.code = code if code is not None else status_code * 100
        self.detail = detail
        super().__init__(self.message)


# =============================================================================
# 错误码常量 — 依据 API §1.7 通用错误码 + §1.8 业务错误码
# =============================================================================

# ---------- 通用错误码（API §1.7）----------
ERR_UNAUTHORIZED = 40100       # 未携带 JWT 或 JWT 无效
ERR_TOKEN_EXPIRED = 40101      # access_token 已过期
ERR_FORBIDDEN = 40300           # 权限不足
ERR_NOT_FOUND = 40400           # 资源不存在
ERR_VALIDATION = 42200         # 参数校验失败
ERR_RATE_LIMITED = 42900       # 触发限流
ERR_BAD_REQUEST = 40000        # 请求参数业务校验失败
ERR_THIRD_PARTY = 50200       # 第三方服务不可用
ERR_INTERNAL = 50000           # 服务端内部错误

# ---------- 业务错误码（API §1.8）----------
ERR_FILE_NOT_UPLOADED = 40010  # 文件尚未上传完成
ERR_BUSINESS_VALIDATION = 40011  # 枚举值/取值范围校验
ERR_RESOURCE_OWNERSHIP = 40310  # 无权操作他人资源
ERR_FILE_NOT_FOUND = 40410      # 文件记录不存在
ERR_MATCH_NOT_FOUND = 40411     # 比赛不存在
ERR_REPORT_NOT_FOUND = 40412    # 分析报告不存在
ERR_RECORD_NOT_FOUND = 40413    # 比赛记录不存在
ERR_SHARE_TOKEN_INVALID = 40414  # 分享 Token 无效或已过期
ERR_MATCH_STATE_CONFLICT = 40910  # 比赛不在进行中
ERR_RECORD_LINKED = 40911        # 比赛记录已关联记分牌
ERR_SCORE_INVALID = 42210       # 比分不符合赛制规则
ERR_QUOTA_EXHAUSTED = 42910     # 免费分析额度耗尽


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    AppException 全局处理器 — 统一捕获 AppException 并返回标准 JSON 响应。

    响应格式：{"code": ..., "message": "...", "data": null, "timestamp": "..."}
    """
    from datetime import datetime, timezone

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    通用异常处理器 — 捕获未处理的异常，返回 500。
    """
    import logging
    from datetime import datetime, timezone

    logging.getLogger(__name__).exception(
        "Unhandled exception: %s | path=%s", str(exc), request.url.path
    )

    return JSONResponse(
        status_code=500,
        content={
            "code": ERR_INTERNAL,
            "message": "服务暂时不可用，请稍后重试",
            "data": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
