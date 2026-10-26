"""
app/schemas/payment.py — 支付模块 Pydantic Schema

依据：切片 11-payment/backend.md §4
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field
from typing import Literal


# ---------------------------------------------------------------------------
# 分页泛型（R4-Pay-3）— 统一分页响应结构
# ---------------------------------------------------------------------------
T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    """通用分页响应 Schema"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    items: List[T] = Field(default_factory=list, description="当前页数据")


# 订单分页响应类型别名
PaginatedOrders = Paginated["OrderBrief"]


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
