/**
 * usePaymentNotify — WebSocket 支付成功监听（11-payment/frontend.md §4.3）
 *
 * 监听后端 PaymentService._push_payment_success_ws 推送的
 * {event:'payment_success', data:{order_id, product_type}}，
 * 刷新订单列表 + 回调 onSuccess（会员页传 refreshAll → 权益即时刷新，
 * 实施计划 FS6「支付 WS」行）。
 *
 * FS6-P3（与设计 §4.3 样例差异，按工程现实落地）：
 * - 样例经 Taro.eventCenter.on('ws:message') 订阅——本工程 useWebSocket 为
 *   options.onMessage 直回调（FS1 API），无 eventCenter 分发层，改经
 *   useBadgeUnlock 同构模式消费（P3 注记 11-payment §4.3）
 * - 样例在此 Toast 支付成功——Toast 移至 create 页支付回调唯一出口，
 *   避免会员中心→支付页页面栈共存时双 Toast；本 Hook 只做数据刷新（幂等）
 */
import { useCallback, useRef } from 'react'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import { usePaymentStore } from '@/stores/paymentStore'

/**
 * 监听 payment_success WS 事件。
 * 在会员中心页 / 订单列表页挂载：支付完成后订单与权益即时刷新。
 * @param onSuccess - 收到事件的回调（order_id, product_type）
 */
export function usePaymentNotify(onSuccess?: (orderId: number, productType: string) => void) {
  const { fetchOrders } = usePaymentStore()
  const onSuccessRef = useRef(onSuccess)
  onSuccessRef.current = onSuccess

  const onMessage = useCallback(
    (msg: { event?: string; data?: { order_id?: number; product_type?: string } }) => {
      if (msg.event !== 'payment_success') return
      const { order_id: orderId, product_type: productType } = msg.data || {}
      // 刷新订单列表（幂等）
      fetchOrders()
      // 权益即时刷新等回调（挂载方注入）
      onSuccessRef.current?.(orderId ?? 0, productType ?? '')
    },
    [fetchOrders]
  )

  useWebSocket(buildWsUrl(), { onMessage })
}

export default usePaymentNotify
