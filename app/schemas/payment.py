"""
app/schemas/payment.py — 支付模块 Pydantic Schema

依据：切片 11-payment/backend.md §4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from typing import Literal


# --- 请求 Schema ---
class OrderCreateRequest(BaseModel):
    """创建订单请求"""
    product_type: Literal["membership", "analysis_pack"] = Field(
        ..., description="产品类型",
    )
    tier: Optional[str] = Field(default=None, description="会员等级：member/pro/coach")
    period: Optional[str] = Field(
        default=None, description="订阅周期：monthly/quarterly/yearly",
    )
    quantity: Optional[int] = Field(default=1, ge=1, description="分析次数包数量")
    payment_method: Literal["wechat_jsapi", "wechat_app"] = Field(
        default="wechat_jsapi", description="支付方式",
    )


class RefundRequest(BaseModel):
    """退款请求"""
    refund_amount_cents: int = Field(..., gt=0, description="退款金额（分）")
    reason: str = Field(..., min_length=1, max_length=500, description="退款原因")


# --- 响应 Schema ---
class PaymentParams(BaseModel):
    """微信支付参数"""
    prepay_id: str
    pay_sign: str
    timestamp: str
    nonce_str: str


class OrderCreateResponse(BaseModel):
    """创建订单响应"""
    order_id: int
    order_no: str
    amount_cents: int
    payment_params: PaymentParams
    model_config = {"from_attributes": True}


class OrderBrief(BaseModel):
    """订单摘要"""
    id: int
    order_no: str
    product_type: str
    amount_cents: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class RefundResponse(BaseModel):
    """退款响应"""
    order_id: int
    refund_status: str
    refund_amount_cents: int


# --- 微信回调相关 ---
class WechatNotifyResponse(BaseModel):
    """微信回调响应（非统一响应格式）"""
    code: str = "SUCCESS"
    message: str = "成功"
