/**
 * paymentStore 状态机测试（04-前端实施计划.md FS6）
 * 覆盖：createOrder、JSAPI 拉起参数组装（package/signType RSA）、
 * 支付取消、pollOrderStatus 降级轮询（实施计划「降级路径」）、fetchOrders
 */
import Taro from '@tarojs/taro'
import * as paymentApi from '@/services/payment'
import { usePaymentStore } from '@/stores/paymentStore'

jest.mock('@/services/payment', () => ({
  __esModule: true,
  createOrder: jest.fn(),
  listOrders: jest.fn(),
}))

const createOrder = paymentApi.createOrder as jest.Mock
const listOrders = paymentApi.listOrders as jest.Mock
const requestPayment = Taro.requestPayment as jest.Mock

const PAYMENT_PARAMS = {
  prepay_id: 'wx20261',
  pay_sign: 'SIG==',
  timestamp: '1799000000',
  nonce_str: 'n0nce',
}

const ORDER_CREATE_RESULT = {
  data: {
    data: {
      order_id: 42,
      order_no: 'NO202611',
      amount_cents: 1900,
      payment_params: PAYMENT_PARAMS,
    },
  },
}

describe('paymentStore', () => {
  beforeEach(() => {
    jest.resetAllMocks()
    usePaymentStore.setState({
      orders: [],
      orderTotal: 0,
      createResult: null,
      loading: false,
      paying: false,
    })
  })

  it('createOrder 写入 createResult 并穿透返回（供拉起支付）', async () => {
    createOrder.mockResolvedValueOnce(ORDER_CREATE_RESULT)
    const result = await usePaymentStore.getState().createOrder({
      product_type: 'membership', tier: 'member', period: 'monthly', payment_method: 'wechat_jsapi',
    })
    expect(createOrder).toHaveBeenCalledWith({
      product_type: 'membership', tier: 'member', period: 'monthly', payment_method: 'wechat_jsapi',
    })
    expect(result?.order_id).toBe(42)
    expect(usePaymentStore.getState().createResult).toBe(ORDER_CREATE_RESULT.data.data)
  })

  it('requestWechatPay JSAPI 参数组装：package=prepay_id 拼接 + signType RSA', async () => {
    requestPayment.mockResolvedValueOnce({})
    const ok = await usePaymentStore.getState().requestWechatPay(PAYMENT_PARAMS)
    expect(ok).toBe(true)
    expect(requestPayment).toHaveBeenCalledWith({
      timeStamp: '1799000000',
      nonceStr: 'n0nce',
      package: 'prepay_id=wx20261',
      signType: 'RSA',
      paySign: 'SIG==',
    })
    expect(usePaymentStore.getState().paying).toBe(false)
  })

  it('requestWechatPay 用户取消/失败 → false（paying 复位）', async () => {
    requestPayment.mockRejectedValueOnce(new Error('cancel'))
    const ok = await usePaymentStore.getState().requestWechatPay(PAYMENT_PARAMS)
    expect(ok).toBe(false)
    expect(usePaymentStore.getState().paying).toBe(false)
  })

  it('pollOrderStatus 轮询确认订单转 paid（WS 未达/回调延迟兜底）', async () => {
    const pendingPage = (orderId: number) => ({
      data: { data: { total: 1, page: 1, page_size: 50, items: [
        { id: orderId, order_no: 'NO', product_type: 'membership', amount_cents: 1900, status: 'pending', created_at: 't', paid_at: null },
      ] } },
    })
    const paidPage = (orderId: number) => ({
      data: { data: { total: 1, page: 1, page_size: 50, items: [
        { id: orderId, order_no: 'NO', product_type: 'membership', amount_cents: 1900, status: 'paid', created_at: 't', paid_at: 't2' },
      ] } },
    })
    listOrders
      .mockResolvedValueOnce(pendingPage(42)) // 第 1 次：回调未到
      .mockResolvedValueOnce(paidPage(42)) // 第 2 次：已支付
    const confirmed = await usePaymentStore.getState().pollOrderStatus(42, 6, 0)
    expect(confirmed).toBe(true)
    expect(listOrders).toHaveBeenCalledTimes(2)
  })

  it('pollOrderStatus 超过轮询上限仍未 paid → false（用户可在订单页查看 pending 态）', async () => {
    const pendingPage = {
      data: { data: { total: 1, page: 1, page_size: 50, items: [
        { id: 42, order_no: 'NO', product_type: 'membership', amount_cents: 1900, status: 'pending', created_at: 't', paid_at: null },
      ] } },
    }
    listOrders.mockResolvedValue(pendingPage)
    const confirmed = await usePaymentStore.getState().pollOrderStatus(42, 3, 0)
    expect(confirmed).toBe(false)
    expect(listOrders).toHaveBeenCalledTimes(3)
  })

  it('fetchOrders 状态筛选 + 固定 page_size=50', async () => {
    listOrders.mockResolvedValueOnce({
      data: { data: { total: 5, page: 1, page_size: 50, items: [
        { id: 1, order_no: 'NO1', product_type: 'membership', amount_cents: 1900, status: 'paid', created_at: 't', paid_at: 't' },
      ] } },
    })
    await usePaymentStore.getState().fetchOrders({ status: 'paid' })
    const s = usePaymentStore.getState()
    expect(listOrders).toHaveBeenCalledWith({ status: 'paid', page: 1, page_size: 50 })
    expect(s.orders).toHaveLength(1)
    expect(s.orderTotal).toBe(5)
  })
})
