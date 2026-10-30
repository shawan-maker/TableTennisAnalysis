"""
app/api/v1/payment/router.py — 支付模块 API 路由

依据：切片 11-payment/backend.md §6
      API §12 payment 端点（4 个）
注意：/payment/notify 响应格式偏离统一规范（微信 V3 协议要求）
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.deps import get_current_user, get_current_admin
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.payment import (
    OrderCreateRequest, RefundRequest,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payment", tags=["支付"])


@router.post("/orders", summary="创建订单")
@limiter.limit("100/minute")
async def create_order(
    body: OrderCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建订单（会员订阅/分析次数包），返回微信支付参数"""
    data = await PaymentService.create_order(
        user.id, body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return success(data=data, message="订单已创建")


@router.get("/orders", summary="订单列表")
@limiter.limit("100/minute")
async def list_orders(
    request: Request,
    status: str | None = Query(default=None, description="状态过滤"),
    product_type: str | None = Query(default=None, description="产品类型过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """获取当前用户订单列表（分页）"""
    data = await PaymentService.list_orders(
        user_id=user.id,
        status=status,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )
    return success(data=data)


# SEC-006: 微信回调不被限流（微信服务器需要立即收到响应）
@router.post("/notify", summary="微信支付回调")
async def payment_notify(
    request: Request,
):
    """
    微信支付异步回调（V3 APIv3）。
    权限：微信签名验证（无需 JWT）。
    返回微信要求的响应格式（非统一响应格式）。
    """
    signature = request.headers.get("Wechatpay-Signature", "")
    serial = request.headers.get("Wechatpay-Serial", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")

    body = (await request.body()).decode()

    result = await PaymentService.handle_notify(
        signature=signature,
        serial=serial,
        nonce=nonce,
        timestamp=timestamp,
        body=body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    status_code = 200 if result.get("code") == "SUCCESS" else 400
    return JSONResponse(
        status_code=status_code,
        content=result,
    )


@router.post("/orders/{order_id}/refund", summary="申请退款")
@limiter.limit("100/minute")
async def refund_order(
    order_id: int,
    body: RefundRequest,
    request: Request,
    user: User = Depends(get_current_admin),
):
    """申请退款（管理员操作 — JWT 认证）"""
    data = await PaymentService.refund(
        order_id=order_id,
        refund_amount_cents=body.refund_amount_cents,
        reason=body.reason,
        operator_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return success(data=data, message="退款申请已提交")
