"""
app/services/payment_service.py — 支付业务逻辑层

依据：切片 11-payment/backend.md §5
      模块详细设计 §2.11 / API §12
开发模式：WECHAT_PAY_MOCK=True 时跳过真实微信支付 API 调用
"""

import base64
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.pagination import paginate, PaginationParams
from app.models.payment import Order, PaymentRecord, RefundRecord
from app.models.membership import Subscription, MembershipTierConfig
from app.models.admin import AuditLog
from app.schemas.payment import (
    OrderCreateRequest, OrderCreateResponse, OrderBrief,
    PaymentParams, RefundRequest, RefundResponse,
)
from app.services.membership_service import MembershipService

logger = logging.getLogger(__name__)

# 分析次数包定价
ANALYSIS_PACK_PRICING = {1: 1500, 3: 3900, 10: 9900}

# 订阅周期映射
PERIOD_DELTA = {
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=90),
    "yearly": timedelta(days=365),
}


class PaymentService:
    """支付业务逻辑层"""

    WECHAT_UNIFIED_ORDER_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
    WECHAT_REFUND_URL = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"

    # ==================== 订单创建 ====================

    @staticmethod
    async def create_order(
        user_id: int, req: OrderCreateRequest,
        ip_address: str | None = None, user_agent: str | None = None,
    ) -> OrderCreateResponse:
        """创建订单 → 调用微信统一下单 → 返回支付参数"""
        order_no = f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"

        async with async_session_factory() as db:
            amount_cents = await PaymentService._calculate_amount(db, req)

            if req.product_type == "membership":
                period_days = int(PERIOD_DELTA.get(req.period, timedelta(days=30)).total_seconds() // 86400)
                extra_data = {"tier": req.tier, "period_days": period_days, "period": req.period}
            elif req.product_type == "analysis_pack":
                extra_data = {"quantity": req.quantity or 1}
            else:
                extra_data = None

            order = Order(
                user_id=user_id,
                order_no=order_no,
                product_type=req.product_type,
                amount_cents=amount_cents,
                status="pending",
                extra_data=extra_data,
            )
            db.add(order)
            await db.flush()

            # 调用微信统一下单
            try:
                wx_params = await PaymentService._call_wechat_unified_order(
                    order_no=order_no,
                    amount_cents=amount_cents,
                    description=PaymentService._get_product_description(req),
                    user_id=user_id,
                    payment_method=req.payment_method,
                )
            except AppException:
                await db.delete(order)
                await db.commit()
                raise
            except Exception as e:
                await db.delete(order)
                await db.commit()
                raise AppException(f"支付服务暂时不可用: {str(e)}", 502)

            # 审计日志
            audit_entry = AuditLog(
                user_id=user_id,
                action="payment_order_created",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "amount": amount_cents,
                    "product_type": req.product_type,
                    "tier": req.tier,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()
            await db.refresh(order)

            return OrderCreateResponse(
                order_id=order.id,
                order_no=order.order_no,
                amount_cents=order.amount_cents,
                payment_params=PaymentParams(
                    prepay_id=wx_params["prepay_id"],
                    pay_sign=wx_params["pay_sign"],
                    timestamp=wx_params["timestamp"],
                    nonce_str=wx_params["nonce_str"],
                ),
            )

    @staticmethod
    async def _calculate_amount(db: AsyncSession, req: OrderCreateRequest) -> int:
        """根据产品类型计算金额（分），会员定价从 DB 查询"""
        if req.product_type == "membership":
            if not req.tier or not req.period:
                raise AppException("会员等级或周期参数不合法", 422)
            result = await db.execute(
                select(MembershipTierConfig).where(MembershipTierConfig.tier == req.tier)
            )
            tier_config = result.scalar_one_or_none()
            if not tier_config:
                raise AppException("会员等级或周期参数不合法", 422)
            price_map = {
                "monthly": tier_config.price_monthly_cents,
                "quarterly": tier_config.price_quarterly_cents,
                "yearly": tier_config.price_yearly_cents,
            }
            amount = price_map.get(req.period)
            if not amount:
                raise AppException("会员等级或周期参数不合法", 422)
            return amount

        elif req.product_type == "analysis_pack":
            qty = req.quantity or 1
            amount = ANALYSIS_PACK_PRICING.get(qty)
            if not amount:
                raise AppException("分析次数包数量不合法", 422)
            return amount

        else:
            raise AppException("产品类型不合法", 422)

    @staticmethod
    def _get_product_description(req: OrderCreateRequest) -> str:
        """生成产品描述"""
        if req.product_type == "membership":
            return f"乒乓智能分析-{req.tier}会员-{req.period}"
        elif req.product_type == "analysis_pack":
            return f"乒乓智能分析-分析次数包x{req.quantity}"
        return "乒乓智能分析"

    @staticmethod
    async def _call_wechat_unified_order(
        order_no: str, amount_cents: int, description: str,
        user_id: int, payment_method: str,
    ) -> dict:
        """调用微信统一下单 API（V3）。MOCK 模式返回模拟参数。"""
        if settings.WECHAT_PAY_MOCK:
            logger.info("MOCK wechat unified order: order_no=%s", order_no)
            return {
                "prepay_id": f"mock_prepay_{uuid.uuid4().hex[:16]}",
                "pay_sign": "mock_sign_" + uuid.uuid4().hex[:16],
                "timestamp": str(int(time.time())),
                "nonce_str": uuid.uuid4().hex,
            }

        # 真实微信下单
        from app.models.user import User
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user or not user.openid:
                raise AppException("用户信息不完整，无法发起支付", 400)

        payload = {
            "appid": settings.WECHAT_APPID,
            "mchid": settings.WECHAT_MCH_ID,
            "description": description,
            "out_trade_no": order_no,
            "notify_url": settings.WECHAT_NOTIFY_URL,
            "amount": {"total": amount_cents, "currency": "CNY"},
            "payer": {"openid": user.openid},
        }

        headers = PaymentService._build_wechat_headers("POST", "/v3/pay/transactions/jsapi")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                PaymentService.WECHAT_UNIFIED_ORDER_URL,
                json=payload, headers=headers, timeout=15,
            )

        if resp.status_code != 200:
            error_data = resp.json()
            raise AppException(f"微信统一下单失败: {error_data.get('message', 'unknown')}", 502)

        data = resp.json()
        prepay_id = data.get("prepay_id")
        if not prepay_id:
            raise AppException("微信下单返回异常", 502)

        timestamp = str(int(time.time()))
        nonce_str = uuid.uuid4().hex
        package = f"prepay_id={prepay_id}"
        sign_str = f"{settings.WECHAT_APPID}\n{timestamp}\n{nonce_str}\n{package}\n"
        pay_sign = PaymentService._rsa_sign(sign_str)

        return {
            "prepay_id": prepay_id, "pay_sign": pay_sign,
            "timestamp": timestamp, "nonce_str": nonce_str,
        }

    @staticmethod
    def _build_wechat_headers(method: str, url: str) -> dict:
        """构建微信 API 请求头（含签名）"""
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        sign_str = f"{method}\n{url}\n{timestamp}\n{nonce}\n\n"
        signature = PaymentService._rsa_sign(sign_str)
        auth = (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.WECHAT_MCH_ID}",'
            f'nonce_str="{nonce}",timestamp="{timestamp}",'
            f'serial_no="{settings.WECHAT_CERT_SERIAL}",signature="{signature}"'
        )
        return {
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _rsa_sign(data: str) -> str:
        """RSA-SHA256 签名"""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key_pem = settings.WECHAT_PRIVATE_KEY.encode()
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        signature = private_key.sign(
            data.encode(), padding.PKCS1v15(), hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    # ==================== 订单列表 ====================

    @staticmethod
    async def list_orders(
        user_id: int,
        status: Optional[str] = None,
        product_type: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """获取当前用户订单列表"""
        async with async_session_factory() as db:
            stmt = select(Order).where(Order.user_id == user_id)
            if status:
                stmt = stmt.where(Order.status == status)
            if product_type:
                stmt = stmt.where(Order.product_type == product_type)
            stmt = stmt.order_by(desc(Order.created_at))

            pagination = PaginationParams(page=page, page_size=page_size)
            result = await paginate(db, stmt, pagination)

            return {
                "total": result["total"], "page": page, "page_size": page_size,
                "items": [OrderBrief.model_validate(o) for o in result["items"]],
            }

    # ==================== 微信支付回调 ====================

    @staticmethod
    async def handle_notify(
        signature: str, serial: str, nonce: str, timestamp: str,
        body: str,
        ip_address: str | None = None, user_agent: str | None = None,
    ) -> dict:
        """微信支付异步回调处理（V3 APIv3）"""
        # 1. 验签
        if not await PaymentService._verify_signature(signature, serial, nonce, timestamp, body):
            return {"code": "FAIL", "message": "签名验证失败"}

        # 2. 解析回调 body
        try:
            callback = json.loads(body)
        except json.JSONDecodeError:
            return {"code": "FAIL", "message": "回调数据格式错误"}

        # 3. 解密
        resource = callback.get("resource", {})
        try:
            decrypted = PaymentService._decrypt_callback(resource)
        except Exception:
            return {"code": "FAIL", "message": "解密失败"}

        out_trade_no = decrypted.get("out_trade_no")
        trade_state = decrypted.get("trade_state")
        transaction_id = decrypted.get("transaction_id")
        amount_total = decrypted.get("amount", {}).get("total")

        async with async_session_factory() as db:
            result = await db.execute(
                select(Order).where(Order.order_no == out_trade_no)
            )
            order = result.scalar_one_or_none()

            if not order:
                return {"code": "FAIL", "message": "订单不存在"}

            # 5. 幂等处理
            if order.status == "paid":
                return {"code": "SUCCESS", "message": "成功"}

            # 6. 验证交易状态
            if trade_state != "SUCCESS":
                return {"code": "FAIL", "message": f"交易状态异常: {trade_state}"}

            # 7. 更新订单状态
            order.status = "paid"
            order.paid_at = datetime.now(timezone.utc)

            # 8. 创建支付记录
            payment = PaymentRecord(
                order_id=order.id,
                transaction_id=transaction_id,
                payment_method="wechat_jsapi",
                amount_cents=amount_total or order.amount_cents,
                callback_raw=decrypted,
                paid_at=datetime.now(timezone.utc),
            )
            db.add(payment)

            # 9. 触发业务逻辑
            await PaymentService._trigger_business_logic(db, order, ip_address=ip_address)

            # 审计日志
            audit_entry = AuditLog(
                user_id=order.user_id,
                action="payment_callback_processed",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "transaction_id": transaction_id,
                    "amount": amount_total or order.amount_cents,
                    "status": order.status,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()

            # 10. 推送支付成功通知
            try:
                await PaymentService._push_payment_success_ws(
                    order.user_id, order.id, order.product_type,
                )
            except Exception as e:
                logger.warning("push payment success ws failed: %s", e)

            return {"code": "SUCCESS", "message": "成功"}

    @staticmethod
    async def _verify_signature(
        signature: str, serial: str, nonce: str, timestamp: str, body: str,
    ) -> bool:
        """验证微信支付回调签名。MOCK 模式直接返回 True。"""
        if settings.WECHAT_PAY_MOCK:
            return True

        sign_str = f"{timestamp}\n{nonce}\n{body}\n"
        cert_pubkey = await PaymentService._get_wechat_platform_cert(serial)
        if not cert_pubkey:
            return False

        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            pub_key = load_pem_public_key(cert_pubkey.encode())
            signature_bytes = base64.b64decode(signature)
            pub_key.verify(
                signature_bytes, sign_str.encode(),
                padding.PKCS1v15(), hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def _get_wechat_platform_cert(serial: str) -> Optional[str]:
        """从 Redis 获取微信平台证书公钥"""
        try:
            redis = await get_redis()
            return await redis.get(f"wechat:platform_cert:{serial}")
        except Exception:
            return None

    @staticmethod
    def _decrypt_callback(resource: dict) -> dict:
        """解密微信回调 ciphertext。MOCK 模式直接返回 resource。"""
        if settings.WECHAT_PAY_MOCK:
            # MOCK 模式：resource 本身就是明文
            return resource

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        ciphertext = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        ciphertext_bytes = base64.b64decode(ciphertext)
        api_v3_key = settings.WECHAT_API_V3_KEY.encode()  # 32 字节密钥
        aesgcm = AESGCM(api_v3_key)
        decrypted = aesgcm.decrypt(
            nonce=nonce.encode(),
            data=ciphertext_bytes,
            associated_data=associated_data.encode() if associated_data else None,
        )
        return json.loads(decrypted.decode())

    @staticmethod
    async def _trigger_business_logic(
        db: AsyncSession, order: Order,
        ip_address: str | None = None,
    ):
        """支付成功后根据订单类型触发对应业务逻辑"""
        if order.product_type == "membership":
            await PaymentService._create_or_renew_subscription(db, order, ip_address=ip_address)

        elif order.product_type == "analysis_pack":
            redis = await get_redis()
            extra = order.extra_data or {}
            bonus_qty = extra.get("quantity", 1)
            await redis.incrby(f"quota:bonus:{order.user_id}", bonus_qty)
            await redis.expire(f"quota:bonus:{order.user_id}", 7776000)

    @staticmethod
    async def _create_or_renew_subscription(
        db: AsyncSession, order: Order,
        ip_address: str | None = None,
    ):
        """创建或续期会员订阅"""
        extra = order.extra_data or {}
        tier = extra.get("tier", "member")
        period_days = extra.get("period_days", 30)

        result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == order.user_id,
                Subscription.status.in_(["active", "expiring_soon"]),
            )
        )
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing:
            start = max(existing.expire_at, now) if existing.expire_at else now
            existing.expire_at = start + timedelta(days=period_days)
            existing.status = "active"
            existing.tier = tier  # 更新等级（可能从 free 升级为 member）
            subscription_id = existing.id
        else:
            sub = Subscription(
                user_id=order.user_id, tier=tier, status="active",
                start_at=now, expire_at=now + timedelta(days=period_days),
            )
            db.add(sub)
            await db.flush()
            order.subscription_id = sub.id
            subscription_id = sub.id

        audit_entry = AuditLog(
            user_id=order.user_id,
            action="subscription_created_or_renewed",
            target_type="subscription",
            target_id=subscription_id,
            detail=json.dumps({
                "tier": tier,
                "period": extra.get("period", "monthly"),
            }),
            ip_address=ip_address,
        )
        db.add(audit_entry)

    @staticmethod
    async def _push_payment_success_ws(
        user_id: int, order_id: int, product_type: str,
    ):
        """通过 WebSocket 推送支付成功通知"""
        from app.services.notification_service import NotificationService
        await NotificationService.push_ws_message(
            user_id=user_id,
            event_type="payment_success",
            data={"order_id": order_id, "product_type": product_type},
        )

    # ==================== 退款 ====================

    @staticmethod
    async def refund(
        order_id: int, refund_amount_cents: int, reason: str,
        operator_id: int | None = None,
        ip_address: str | None = None, user_agent: str | None = None,
    ) -> RefundResponse:
        """申请退款（管理员操作）"""
        async with async_session_factory() as db:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()

            if not order:
                raise AppException("订单不存在", 404)

            if order.status != "paid":
                raise AppException("仅已支付订单可退款", 400)

            if refund_amount_cents > order.amount_cents:
                raise AppException("退款金额不能超过订单金额", 400)

            # 退款时间窗口校验
            if order.paid_at:
                elapsed = datetime.now(timezone.utc) - order.paid_at
                if elapsed > timedelta(days=7):
                    raise AppException("超过7天的订单不可退款", 422)
                if refund_amount_cents < order.amount_cents:
                    reversal_type = "partial"
                elif elapsed <= timedelta(hours=24):
                    reversal_type = "full"
                else:
                    reversal_type = "full_reversal"
            else:
                reversal_type = "full"

            refund_no = f"RF{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"

            # 调用微信退款 API
            try:
                wx_resp = await PaymentService._call_wechat_refund(
                    order_no=order.order_no, refund_no=refund_no,
                    refund_amount_cents=refund_amount_cents,
                    total_amount_cents=order.amount_cents, reason=reason,
                )
            except AppException:
                raise
            except Exception as e:
                raise AppException(f"退款服务暂时不可用: {str(e)}", 502)

            refund_record = RefundRecord(
                order_id=order.id, refund_no=refund_no,
                refund_amount_cents=refund_amount_cents, reason=reason,
                status="pending", reversal_type=reversal_type,
                operator_id=operator_id, callback_raw=wx_resp,
            )
            db.add(refund_record)

            order.status = "refunded"

            audit_entry = AuditLog(
                user_id=operator_id,
                action="refund",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "refund_amount": refund_amount_cents,
                    "operator_id": operator_id,
                    "reason": reason,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()

            # 退款后撤销会员权益
            if order.product_type == "membership" and order.subscription_id:
                await MembershipService.revoke_subscription(db, order.subscription_id)

            return RefundResponse(
                order_id=order.id,
                refund_status="pending",
                refund_amount_cents=refund_amount_cents,
            )

    @staticmethod
    async def _call_wechat_refund(
        order_no: str, refund_no: str,
        refund_amount_cents: int, total_amount_cents: int, reason: str,
    ) -> dict:
        """调用微信退款 API。MOCK 模式返回模拟响应。"""
        if settings.WECHAT_PAY_MOCK:
            logger.info("MOCK wechat refund: refund_no=%s", refund_no)
            return {
                "refund_id": f"mock_refund_{uuid.uuid4().hex[:16]}",
                "status": "PROCESSING",
            }

        payload = {
            "out_trade_no": order_no,
            "out_refund_no": refund_no,
            "reason": reason,
            "amount": {
                "refund": refund_amount_cents,
                "total": total_amount_cents,
                "currency": "CNY",
            },
        }

        headers = PaymentService._build_wechat_headers("POST", "/v3/refund/domestic/refunds")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                PaymentService.WECHAT_REFUND_URL,
                json=payload, headers=headers, timeout=15,
            )

        if resp.status_code != 200:
            error_data = resp.json()
            raise AppException(f"微信退款失败: {error_data.get('message', 'unknown')}", 502)

        return resp.json()
