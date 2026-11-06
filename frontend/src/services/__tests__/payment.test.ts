/**
 * payment Service 契约测试（04-前端实施计划.md FS6）
 * 用户态 2 端点（POST /payment/orders、GET /payment/orders）；
 * /notify 为微信回调、/refund 为 get_current_admin 端点，不对小程序前端暴露
 */
import request from '@/services/request'
import * as paymentApi from '@/services/payment'
import type { OrderCreateParams, OrderBrief, PaymentParams } from '@/services/payment'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const get = request.get as jest.Mock
const post = request.post as jest.Mock

describe('payment Service 契约（router.py 用户态 2 端点）', () => {
  beforeEach(() => jest.resetAllMocks())

  it('POST /payment/orders — createOrder 携带 OrderCreateRequest 体', async () => {
    const payload = { data: { data: { order_id: 1 } } }
    post.mockResolvedValueOnce(payload)
    const params: OrderCreateParams = {
      product_type: 'membership',
      tier: 'member',
      period: 'monthly',
      payment_method: 'wechat_jsapi',
    }
    const res = await paymentApi.createOrder(params)
    expect(post).toHaveBeenCalledWith('/payment/orders', params)
    expect(res).toBe(payload)
  })

  it('GET /payment/orders — listOrders 分页参数透传', async () => {
    const payload = { data: { data: { total: 0, items: [] } } }
    get.mockResolvedValueOnce(payload)
    const res = await paymentApi.listOrders({ status: 'paid', page: 1, page_size: 50 })
    expect(get).toHaveBeenCalledWith('/payment/orders', {
      status: 'paid', page: 1, page_size: 50,
    })
    expect(res).toBe(payload)
  })

  it('listOrders 无参调用（可选参数）', async () => {
    get.mockResolvedValueOnce({ data: { data: {} } })
    await paymentApi.listOrders()
    expect(get).toHaveBeenCalledWith('/payment/orders', undefined)
  })
})

describe('编译期契约（schemas/payment.py）', () => {
  it('PaymentParams JSAPI 四字段（package 组装归 store）', () => {
    const params: PaymentParams = {
      prepay_id: 'wx1', pay_sign: 'sig', timestamp: '1700000000', nonce_str: 'n1',
    }
    expect(params.prepay_id).toBe('wx1')
  })

  it('OrderBrief 状态机四态 pending/paid/refunded/cancelled（ refunded 即用户侧退款形态）', () => {
    const order: OrderBrief = {
      id: 1, order_no: 'NO1', product_type: 'membership', amount_cents: 1900,
      status: 'refunded', created_at: '2026-11-06T10:00:00Z', paid_at: '2026-11-06T10:01:00Z',
    }
    expect(order.status).toBe('refunded')
  })
})
