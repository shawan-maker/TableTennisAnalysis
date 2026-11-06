/**
 * payment 模块 API Service（11-payment/frontend.md §2）
 * 端点与后端 app/api/v1/payment/router.py 逐字一致（用户态 2 个；
 * /payment/notify 为微信回调、/refund 为 get_current_admin 管理员端点，均不对前端小程序暴露）。
 *
 * FS6-P3 契约同步：
 * - 订单页无用户退款入口（后端 POST /payment/orders/{id}/refund 为管理员专用，
 *   实施计划「退款入口」以订单状态 refunded 展示形态落地，P3 注记 11-payment §4.2）
 * - weapp 拉起支付参数组装：package=`prepay_id=${prepay_id}` + signType 'RSA'
 *   由 paymentStore.requestWechatPay 完成（设计 §3 同构）
 */
import request from './request'

/** 订单创建参数（app/schemas/payment.py OrderCreateRequest） */
export interface OrderCreateParams {
  product_type: 'membership' | 'analysis_pack'
  tier?: 'member' | 'pro' | 'coach'
  period?: 'monthly' | 'quarterly' | 'yearly'
  quantity?: number
  payment_method: 'wechat_jsapi' | 'wechat_app'
}

/** 支付参数（微信 JSAPI） */
export interface PaymentParams {
  prepay_id: string
  pay_sign: string
  timestamp: string
  nonce_str: string
}

/** 订单创建响应 */
export interface OrderCreateResult {
  order_id: number
  order_no: string
  amount_cents: number
  payment_params: PaymentParams
}

/** 订单摘要（app/schemas/payment.py OrderBrief） */
export interface OrderBrief {
  id: number
  order_no: string
  product_type: string
  amount_cents: number
  status: string // pending/paid/refunded/cancelled
  created_at: string
  paid_at: string | null
}

/** 订单列表响应（app/core/pagination.py Paginated） */
export interface OrderListData {
  total: number
  page: number
  page_size: number
  items: OrderBrief[]
}

/**
 * 创建订单（会员订阅/分析次数包，API §12.1）。
 * 返回微信支付参数，前端调用 Taro.requestPayment 拉起支付。
 * 422：会员等级或周期参数不合法。
 */
export function createOrder(params: OrderCreateParams) {
  return request.post<OrderCreateResult>('/payment/orders', params)
}

/**
 * 获取订单列表（API §12.2，分页）。
 * @param params.status - 状态过滤
 * @param params.product_type - 产品类型过滤
 * @param params.page - 页码（默认 1）
 * @param params.page_size - 每页条数（默认 20，上限 50）
 */
export function listOrders(params?: {
  status?: string
  product_type?: string
  page?: number
  page_size?: number
}) {
  return request.get<OrderListData>('/payment/orders', params)
}
