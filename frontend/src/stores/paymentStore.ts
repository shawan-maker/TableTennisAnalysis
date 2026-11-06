/**
 * 支付状态管理（11-payment/frontend.md §3）
 * JSAPI 拉起：Taro.requestPayment({timeStamp, nonceStr, package, signType:'RSA', paySign})
 *
 * FS6-P3：新增 pollOrderStatus —— 支付回调降级轮询（实施计划 FS6「降级路径」：
 * 支付成功但 payment_success WS 未达/微信回调延迟时，轮询订单列表确认
 * status==='paid'；后端无单订单 GET 端点，走 listOrders 过滤 order_id）。
 */
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as paymentApi from '@/services/payment'
import type { OrderCreateParams, OrderCreateResult } from '@/services/payment'

interface PaymentState {
  orders: paymentApi.OrderBrief[]
  orderTotal: number
  createResult: OrderCreateResult | null
  loading: boolean
  paying: boolean

  // Actions
  fetchOrders: (params?: { status?: string; product_type?: string }) => Promise<void>
  createOrder: (params: OrderCreateParams) => Promise<OrderCreateResult | null>
  requestWechatPay: (paymentParams: paymentApi.PaymentParams) => Promise<boolean>
  /** 支付回调轮询兜底：确认订单转 paid（true=已确认支付成功） */
  pollOrderStatus: (orderId: number, maxAttempts?: number, intervalMs?: number) => Promise<boolean>
  resetCreateResult: () => void
}

export const usePaymentStore = create<PaymentState>((set) => ({
  orders: [],
  orderTotal: 0,
  createResult: null,
  loading: false,
  paying: false,

  fetchOrders: async (params) => {
    set({ loading: true })
    try {
      const res = await paymentApi.listOrders({
        ...params,
        page: 1,
        page_size: 50,
      })
      const data = res.data.data
      set({ orders: data.items, orderTotal: data.total })
    } finally {
      set({ loading: false })
    }
  },

  createOrder: async (params) => {
    set({ loading: true })
    try {
      const res = await paymentApi.createOrder(params)
      const result = res.data.data
      set({ createResult: result })
      return result
    } finally {
      set({ loading: false })
    }
  },

  requestWechatPay: async (paymentParams) => {
    set({ paying: true })
    try {
      // 微信 JSAPI 拉起支付（package 由 prepay_id 组装）
      await Taro.requestPayment({
        timeStamp: paymentParams.timestamp,
        nonceStr: paymentParams.nonce_str,
        package: `prepay_id=${paymentParams.prepay_id}`,
        signType: 'RSA',
        paySign: paymentParams.pay_sign,
      })
      return true
    } catch (err: any) {
      // 用户取消支付或支付失败
      console.error('WeChat payment failed:', err)
      return false
    } finally {
      set({ paying: false })
    }
  },

  pollOrderStatus: async (orderId, maxAttempts = 6, intervalMs = 2000) => {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
      try {
        const res = await paymentApi.listOrders({ page: 1, page_size: 50 })
        const target = res.data.data.items.find((o) => o.id === orderId)
        if (target && target.status === 'paid') {
          return true
        }
      } catch (error) {
        console.error('pollOrderStatus attempt failed', error)
      }
    }
    return false
  },

  resetCreateResult: () => {
    set({ createResult: null })
  },
}))
