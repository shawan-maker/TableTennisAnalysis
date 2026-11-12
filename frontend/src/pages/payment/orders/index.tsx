/**
 * 订单列表页（11-payment/frontend.md §4.2）
 * 状态筛选 Tabs + 订单卡片 + 支付成功 WS 即时刷新。
 *
 * FS6-P3 契约同步：
 * - 实施计划「退款入口」按后端实现落地为状态展示——POST /payment/orders/{id}/refund
 *   为 get_current_admin 管理员端点，用户侧仅 pending→继续支付 / paid→会员已生效
 *   / refunded→已退款 文案展示（与设计 §4.2 样例一致）
 * - usePaymentNotify 挂载即 WS 支付成功后订单列表刷新（Toast 出口在 create 页唯一）
 * - Empty 组件按 NutUI 2.7.14 真实 API 用 title（样例 description 不存在）
 */
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Tag, Tabs, Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { usePaymentStore } from '@/stores/paymentStore'
import { usePaymentNotify } from '@/hooks/usePaymentNotify'
import { formatAmount, formatDate } from '@/utils/payment'
import './orders.scss'

/** 订单状态映射 */
const STATUS_MAP: Record<string, { labelKey: string; color: string }> = {
  pending: { labelKey: 'payment.statusPending', color: 'var(--color-accent)' },
  paid: { labelKey: 'payment.statusPaid', color: 'var(--color-success)' },
  refunded: { labelKey: 'payment.statusRefunded', color: 'var(--color-text-secondary)' },
  cancelled: { labelKey: 'payment.statusCancelled', color: 'var(--color-text-secondary)' },
}

/** 产品类型映射 */
const PRODUCT_TYPE_MAP: Record<string, { labelKey: string; icon: string }> = {
  membership: { labelKey: 'payment.productMembership', icon: '⭐' },
  analysis_pack: { labelKey: 'payment.productAnalysisPack', icon: '📊' },
}

export default function OrderList() {
  const { t } = useTranslation()
  const { orders, orderTotal, loading, fetchOrders } = usePaymentStore()
  const [activeTab, setActiveTab] = useState('all')

  useEffect(() => {
    const status = activeTab === 'all' ? undefined : activeTab
    fetchOrders({ status })
  }, [activeTab, fetchOrders])

  // 支付成功 WS → 订单列表刷新（幂等）
  usePaymentNotify()

  /** 获取状态标签 */
  const getStatusTag = (status: string) => {
    const config = STATUS_MAP[status] || STATUS_MAP.pending
    return (
      <Tag style={{ background: config.color, color: 'var(--color-text-inverse)' }}>
        {t(config.labelKey)}
      </Tag>
    )
  }

  /** 获取产品类型显示 */
  const getProductType = (type: string) => {
    const config = PRODUCT_TYPE_MAP[type] || { icon: '📦', labelKey: 'payment.productMembership' }
    return `${config.icon} ${t(config.labelKey)}`
  }

  return (
    <View className="orders-page">
      {/* 状态筛选 Tab */}
      <Tabs value={activeTab} onChange={(val) => setActiveTab(val as string)}>
        <Tabs.TabPane title={t('payment.status.all')} value="all" />
        <Tabs.TabPane title={t('payment.status.pending')} value="pending" />
        <Tabs.TabPane title={t('payment.status.paid')} value="paid" />
        <Tabs.TabPane title={t('payment.status.refunded')} value="refunded" />
      </Tabs>

      {/* 订单列表 */}
      <ScrollView scrollY className="orders-scroll">
        {loading ? (
          <View className="orders-loading">
            <Skeleton rows={4} visible={loading} />
          </View>
        ) : orders.length === 0 ? (
          <Empty title={t('payment.noOrders')} />
        ) : (
          <View className="order-list">
            {orders.map((order) => (
              <Cell key={order.id} className="order-card">
                {/* 卡片头部 */}
                <View className="order-header">
                  <Text className="order-product">
                    {getProductType(order.product_type)}
                  </Text>
                  {getStatusTag(order.status)}
                </View>

                {/* 卡片内容 */}
                <View className="order-body">
                  <View className="order-info-row">
                    <Text className="info-label">{t('payment.orderNo')}</Text>
                    <Text className="info-value">{order.order_no}</Text>
                  </View>
                  <View className="order-info-row">
                    <Text className="info-label">{t('payment.amount')}</Text>
                    <Text className="info-amount">{formatAmount(order.amount_cents)}</Text>
                  </View>
                  <View className="order-info-row">
                    <Text className="info-label">{t('payment.createdAt')}</Text>
                    <Text className="info-value">{formatDate(order.created_at)}</Text>
                  </View>
                  {order.paid_at && (
                    <View className="order-info-row">
                      <Text className="info-label">{t('payment.paidAt')}</Text>
                      <Text className="info-value">{formatDate(order.paid_at)}</Text>
                    </View>
                  )}
                </View>

                {/* 卡片操作区（状态展示，无用户侧退款操作） */}
                {order.status === 'pending' && (
                  <View className="order-actions">
                    <Text className="action-pay">{t('payment.continuePay')}</Text>
                  </View>
                )}
                {order.status === 'paid' && order.product_type === 'membership' && (
                  <View className="order-actions">
                    <Text className="action-membership">{t('payment.membershipActive')}</Text>
                    {/* R-FE-R1 批次C（FE-P2-20）：「管理续费」短期落地为会员中心入口引导
                        （auto-renew 操作端点与订单关联字段属中期跨栈）；
                        自动续费状态展示在会员页 current-card */}
                    <Text
                      className="action-renew"
                      onClick={() => Taro.navigateTo({ url: '/pages/membership/index' })}
                    >
                      {t('payment.manageRenewal')}
                    </Text>
                  </View>
                )}
              </Cell>
            ))}
          </View>
        )}
        {!loading && orders.length > 0 && orderTotal <= orders.length && (
          <View className="orders-end">
            <Text className="orders-end-text">{t('common.noMore')}</Text>
          </View>
        )}
      </ScrollView>
    </View>
  )
}
