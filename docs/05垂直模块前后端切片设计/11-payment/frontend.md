# payment 模块 — 前端垂直切片设计

> **模块名称**：`payment`
> **前端目录**：`frontend/src/pages/payment/` + `frontend/src/services/payment.ts` + `frontend/src/stores/paymentStore.ts`
> **定位**：订单创建页（选择会员等级 → 微信支付）、订单列表页
> **依据**：前端需求与界面设计 v2.0 §P5.2（会员中心）、§P5.5（我的订单）、API 详细设计 v1.3 §12

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P5.2（会员中心：会员等级权益对比、开通会员 → 微信支付）
- [ ] 阅读前端设计 v2.0 §P5.5（我的订单：订单列表 + 状态筛选）
- [ ] 阅读本模块的 API 契约（§12.1-12.4，4 个端点）
- [ ] 阅读设计系统规范（色彩 `#E63946`/`#1D3557`/`#F4A261`/`#2A9D8F`，8px 间距网格）
- [ ] 确认本切片范围：订单创建页 + 订单列表页 + paymentStore + WS 支付成功通知监听

---

## 2. API Service 模块

```typescript
// frontend/src/services/payment.ts
import request from './request'

/** 订单创建参数 */
export interface OrderCreateParams {
  product_type: 'membership' | 'analysis_pack'
  tier?: 'member' | 'pro' | 'coach'
  period?: 'monthly' | 'quarterly' | 'yearly'
  quantity?: number
  payment_method: 'wechat_jsapi' | 'wechat_app'
}

/** 支付参数 */
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

/** 订单摘要 */
export interface OrderBrief {
  id: number
  order_no: string
  product_type: string
  amount_cents: number
  status: 'pending' | 'paid' | 'refunded' | 'cancelled'
  created_at: string
  paid_at: string | null
}

/**
 * 创建订单（会员订阅/分析次数包）。
 * 返回微信支付参数，前端调用 wx.requestPayment 拉起支付。
 */
export function createOrder(params: OrderCreateParams) {
  return request.post('/payment/orders', params)
}

/**
 * 获取订单列表。
 * @param params.status - 状态过滤
 * @param params.product_type - 产品类型过滤
 * @param params.page - 页码
 * @param params.page_size - 每页条数
 */
export function listOrders(params?: {
  status?: string
  product_type?: string
  page?: number
  page_size?: number
}) {
  return request.get('/payment/orders', params)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/paymentStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as paymentApi from '@/services/payment'
import type { OrderBrief, OrderCreateResult } from '@/services/payment'

interface PaymentState {
  // 订单列表
  orders: OrderBrief[]
  orderTotal: number
  // 创建订单结果
  createResult: OrderCreateResult | null
  // 加载状态
  loading: boolean
  // 支付中
  paying: boolean

  // Actions
  fetchOrders: (params?: { status?: string; product_type?: string }) => Promise<void>
  createOrder: (params: paymentApi.OrderCreateParams) => Promise<OrderCreateResult | null>
  requestWechatPay: (paymentParams: paymentApi.PaymentParams) => Promise<boolean>
  resetCreateResult: () => void
}

export const usePaymentStore = create<PaymentState>((set, get) => ({
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
      // 调用微信小程序支付 API
      const result = await Taro.requestPayment({
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

  resetCreateResult: () => {
    set({ createResult: null })
  },
}))
```

---

## 4. 页面组件

### 4.1 订单创建页（会员等级选择 + 微信支付）

```tsx
// frontend/src/pages/payment/create.tsx
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Radio } from '@tarojs/components'
import { Cell, Button, Tag, Toast, Icon } from '@nutui/nutui-react'
import { usePaymentStore } from '@/stores/paymentStore'
import { useTranslation } from 'react-i18next'
import i18next from 'i18next'
import './create.scss'

/** 会员等级定价配置 */
const MEMBERSHIP_TIERS = [
  {
    tier: 'member',
    nameKey: 'payment.tierMember',
    pricing: { monthly: 1900, quarterly: 4900, yearly: 16800 },
    featureKeys: ['payment.featureUnlimitedAnalysis', 'payment.featureTrainingPlan', 'payment.feature3DTeaching', 'payment.featureHistoryCompare'],
    recommended: true,
    color: 'var(--color-success)',
  },
  {
    tier: 'pro',
    nameKey: 'payment.tierPro',
    pricing: { monthly: 3900, quarterly: 9900, yearly: 35800 },
    featureKeys: ['payment.featureMemberAllRights', 'payment.featureAdvancedAnalysis', 'payment.featureOpponentModeling', 'payment.featureMonthlyReport'],
    recommended: false,
    color: 'var(--color-secondary)',
  },
  {
    tier: 'coach',
    nameKey: 'payment.tierCoach',
    pricing: { monthly: 9900, quarterly: 26900, yearly: 89900 },
    featureKeys: ['payment.featureProAllRights', 'payment.featureStudentManagement', 'payment.featureBatchAnalysis', 'payment.featureCoachTools'],
    recommended: false,
    color: 'var(--color-accent)',
  },
]

/** 周期配置 */
const PERIOD_OPTIONS = [
  { value: 'monthly', labelKey: 'payment.periodMonthly', suffixKey: 'payment.suffixMonthly' },
  { value: 'quarterly', labelKey: 'payment.periodQuarterly', suffixKey: 'payment.suffixQuarterly' },
  { value: 'yearly', labelKey: 'payment.periodYearly', suffixKey: 'payment.suffixYearly' },
]

/** 金额转显示 */
// 货币符号通过 i18n 配置（payment.currencySymbol）
const formatAmount = (cents: number): string => {
  return `${i18next.t('payment.currencySymbol')}${(cents / 100).toFixed(2)}`
}

/** 计算节省金额 */
const calcSavings = (tier: typeof MEMBERSHIP_TIERS[0], period: string): number => {
  const monthly = tier.pricing.monthly
  const periodPrice = tier.pricing[period as keyof typeof tier.pricing]
  if (period === 'quarterly') return monthly * 3 - periodPrice
  if (period === 'yearly') return monthly * 12 - periodPrice
  return 0
}

export default function CreateOrder() {
  const { t } = useTranslation()
  const { createOrder, requestWechatPay, loading, paying } = usePaymentStore()
  const [selectedTier, setSelectedTier] = useState('member')
  const [selectedPeriod, setSelectedPeriod] = useState('monthly')
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 获取当前选中等级 */
  const currentTier = MEMBERSHIP_TIERS.find((t) => t.tier === selectedTier) || MEMBERSHIP_TIERS[0]
  const amountCents = currentTier.pricing[selectedPeriod as keyof typeof currentTier.pricing]
  const savings = calcSavings(currentTier, selectedPeriod)

  /** 提交订单 → 微信支付 */
  const handlePay = useCallback(async () => {
    try {
      // 1. 创建订单
      const result = await createOrder({
        product_type: 'membership',
        tier: selectedTier as 'member' | 'pro' | 'coach',
        period: selectedPeriod as 'monthly' | 'quarterly' | 'yearly',
        payment_method: 'wechat_jsapi',
      })

      if (!result) {
        showToast(t('payment.createOrderFailed'))
        return
      }

      // 2. 调用微信支付
      const paySuccess = await requestWechatPay(result.payment_params)

      if (paySuccess) {
        showToast(t('payment.paySuccess'))
        // 支付成功后延迟跳转
        setTimeout(() => {
          Taro.navigateBack()
        }, 1500)
      } else {
        showToast(t('payment.payCancelled'))
        // 刷新订单列表（订单已创建但未支付）
      }
    } catch (err: any) {
      showToast(err?.message || t('payment.payFailed'))
    }
  }, [selectedTier, selectedPeriod, createOrder, requestWechatPay, t])

  return (
    <View className="payment-create">
      {/* 标题 */}
      <View className="page-header">
        <Text className="page-title">{t('payment.openMembership')}</Text>
        <Text className="page-subtitle">{t('payment.chooseTier')}</Text>
      </View>

      {/* 会员等级选择 */}
      <View className="tier-list">
        {MEMBERSHIP_TIERS.map((tier) => (
          <View
            key={tier.tier}
            className={`tier-card ${selectedTier === tier.tier ? 'selected' : ''}`}
            style={selectedTier === tier.tier ? { borderColor: tier.color } : {}}
            onClick={() => setSelectedTier(tier.tier)}
          >
            {tier.recommended && (
              <Tag style={{ background: 'var(--color-primary)', color: 'var(--color-text-inverse)' }} className="recommend-tag">
                {t('payment.recommended')}
              </Tag>
            )}
            <View className="tier-header">
              <Text className="tier-name" style={{ color: tier.color }}>{t(tier.nameKey)}</Text>
              <Radio
                checked={selectedTier === tier.tier}
                onChange={() => setSelectedTier(tier.tier)}
              />
            </View>
            <View className="tier-features">
              {tier.featureKeys.map((f, i) => (
                <Text key={i} className="feature-item"><Icon name="check" /> {t(f)}</Text>
              ))}
            </View>
          </View>
        ))}
      </View>

      {/* 周期选择 */}
      <View className="period-section">
        <Text className="section-title">{t('payment.selectPeriod')}</Text>
        <View className="period-list">
          {PERIOD_OPTIONS.map((opt) => {
            const price = currentTier.pricing[opt.value as keyof typeof currentTier.pricing]
            const periodSavings = calcSavings(currentTier, opt.value)
            return (
              <View
                key={opt.value}
                className={`period-card ${selectedPeriod === opt.value ? 'selected' : ''}`}
                onClick={() => setSelectedPeriod(opt.value)}
              >
                <Text className="period-label">{t(opt.labelKey)}</Text>
                <Text className="period-price">{formatAmount(price)}</Text>
                {periodSavings > 0 && (
                  <Text className="period-savings">
                    {t('payment.save')} {formatAmount(periodSavings)}
                  </Text>
                )}
              </View>
            )
          })}
        </View>
      </View>

      {/* 底部支付栏 */}
      <View className="bottom-bar">
        <View className="amount-area">
          <Text className="amount-label">{t('payment.payable')}</Text>
          <Text className="amount-value">{formatAmount(amountCents)}</Text>
        </View>
        <Button
          type="primary"
          loading={loading || paying}
          disabled={loading || paying}
          onClick={handlePay}
          className="pay-button"
        >
          {paying ? t('payment.paying') : t('payment.wechatPay')}
        </Button>
      </View>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.2 订单列表页

```tsx
// frontend/src/pages/payment/orders.tsx
import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Cell, Tag, Tabs, Empty, Skeleton } from '@nutui/nutui-react'
import { usePaymentStore } from '@/stores/paymentStore'
import { useTranslation } from 'react-i18next'
import i18next from 'i18next'
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

/** 金额格式化 */
// 货币符号通过 i18n 配置（payment.currencySymbol）
const formatAmount = (cents: number): string => `${i18next.t('payment.currencySymbol')}${(cents / 100).toFixed(2)}`

/** 日期格式化 */
const formatDate = (isoStr: string): string => {
  const d = new Date(isoStr)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}/${day} ${h}:${min}`
}

export default function OrderList() {
  const { t } = useTranslation()
  const { orders, orderTotal, loading, fetchOrders } = usePaymentStore()
  const [activeTab, setActiveTab] = useState('all')

  useEffect(() => {
    const status = activeTab === 'all' ? undefined : activeTab
    fetchOrders({ status })
  }, [activeTab])

  /** 获取状态标签 */
  const getStatusTag = (status: string) => {
    const config = STATUS_MAP[status] || STATUS_MAP.pending
    return (
      <Tag style={{ background: config.color, color: 'var(--color-text-inverse)' }}>
        {t(`payment.status.${status}`)}
      </Tag>
    )
  }

  /** 获取产品类型显示 */
  const getProductType = (type: string) => {
    const config = PRODUCT_TYPE_MAP[type] || { icon: '📦', labelKey: type }
    return `${config.icon} ${t(`payment.productType.${type}`)}`
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
      {loading ? (
        <View className="orders-loading">
          <Skeleton rows={4} loading={loading} />
        </View>
      ) : orders.length === 0 ? (
        <Empty description={t('payment.noOrders')} />
      ) : (
        <View className="order-list">
          {orders.map((order) => (
            <View key={order.id} className="order-card">
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

              {/* 卡片操作区 */}
              {order.status === 'pending' && (
                <View className="order-actions">
                  <Text className="action-pay">{t('payment.continuePay')}</Text>
                </View>
              )}
              {order.status === 'paid' && order.product_type === 'membership' && (
                <View className="order-actions">
                  <Text className="action-membership">{t('payment.membershipActive')}</Text>
                </View>
              )}
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
```

### 4.3 WS 支付成功通知监听 Hook

```tsx
// frontend/src/hooks/usePaymentNotify.ts
import { useEffect } from 'react'
import Taro from '@tarojs/taro'
import { usePaymentStore } from '@/stores/paymentStore'
import { useTranslation } from 'react-i18next'

/**
 * 监听 WebSocket payment_success 事件。
 * 在会员中心页面或订单列表页面使用。
 */
export function usePaymentNotify(onSuccess?: (orderId: number, productType: string) => void) {
  const { fetchOrders } = usePaymentStore()
  const { t } = useTranslation()

  useEffect(() => {
    // 监听 WS 消息（通过全局事件总线）
    const handleWsMessage = (event: any) => {
      const data = event.detail || event
      if (data.event === 'payment_success') {
        const { order_id, product_type } = data.data || data

        // 显示支付成功提示
        Taro.showToast({
          title: t('payment.paySuccess'),
          icon: 'success',
          duration: 2000,
        })

        // 刷新订单列表
        fetchOrders()

        // 回调
        if (onSuccess) {
          onSuccess(order_id, product_type)
        }
      }
    }

    // 注册 WS 事件监听
    Taro.eventCenter.on('ws:message', handleWsMessage)

    return () => {
      Taro.eventCenter.off('ws:message', handleWsMessage)
    }
  }, [fetchOrders, onSuccess, t])
}
```

---

## 5. 样式

```scss
// frontend/src/pages/payment/create.scss
.payment-create {
  min-height: 100vh;
  padding: var(--spacing-md) var(--spacing-md) 80px;
  background: var(--color-background);
}

.page-header {
  text-align: center;
  padding: var(--spacing-lg) 0;

  .page-title {
    display: block;
    font-size: 24px;
    font-weight: bold;
    color: var(--color-primary);
  }

  .page-subtitle {
    display: block;
    margin-top: var(--spacing-xs);
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.tier-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm-md);
}

.tier-card {
  position: relative;
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  border: 2px solid transparent;
  transition: border-color 0.2s;

  &.selected {
    border-color: var(--color-primary);
  }

  .recommend-tag {
    position: absolute;
    top: 0;
    right: 12px;
    transform: translateY(-50%);
  }

  .tier-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-sm-md);

    .tier-name {
      font-size: 18px;
      font-weight: bold;
    }
  }

  .tier-features {
    .feature-item {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      padding: var(--spacing-xs) 0; /* P3-fix: 2px→var(--spacing-xs) */
    }
  }
}

.period-section {
  margin-top: var(--spacing-lg);

  .section-title {
    font-size: 15px;
    font-weight: bold;
    color: var(--color-text-primary);
    display: block;
    margin-bottom: var(--spacing-sm-md);
  }
}

.period-list {
  display: flex;
  gap: var(--spacing-sm-md);

  .period-card {
    flex: 1;
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-sm-md) var(--spacing-sm);
    text-align: center;
    border: 2px solid transparent;
    transition: border-color 0.2s;

    &.selected {
      border-color: var(--color-primary);
      background: color-mix(in srgb, var(--color-primary) 5%, transparent);
    }

    .period-label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
    }

    .period-price {
      display: block;
      font-size: 18px;
      font-weight: bold;
      color: var(--color-primary);
      margin-top: var(--spacing-xs);
    }

    .period-savings {
      display: block;
      font-size: 12px;
      color: var(--color-success);
      margin-top: var(--spacing-xs);
    }
  }
}

.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 64px;
  background: var(--color-card);
  border-top: 1px solid var(--color-divider);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-md);
  z-index: 100;

  .amount-area {
    .amount-label {
      font-size: 12px;
      color: var(--color-text-secondary);
      display: block;
    }

    .amount-value {
      font-size: 24px;
      font-weight: bold;
      color: var(--color-primary);
    }
  }

  .pay-button {
    background: var(--color-primary);
    color: var(--color-text-inverse);
    border-radius: var(--radius-md);
    height: 44px;
    min-width: 120px; /* P3-fix: button min-width for touch target, not spacing */
    font-size: 15px;
  }
}
```

```scss
// frontend/src/pages/payment/orders.scss
.orders-page {
  min-height: 100vh;
  background: var(--color-background);
}

.order-list {
  padding: var(--spacing-sm-md) var(--spacing-md);
}

.order-card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm-md);

  .order-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: var(--spacing-sm-md);
    border-bottom: 1px solid var(--color-divider);

    .order-product {
      font-size: 15px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
  }

  .order-body {
    padding: var(--spacing-sm-md) 0;

    .order-info-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: var(--spacing-xs) 0;

      .info-label {
        font-size: 13px;
        color: var(--color-text-secondary);
      }

      .info-value {
        font-size: 13px;
        color: var(--color-text-primary);
      }

      .info-amount {
        font-size: 15px;
        font-weight: bold;
        color: var(--color-primary);
      }
    }
  }

  .order-actions {
    padding-top: var(--spacing-sm);
    border-top: 1px solid var(--color-divider);

    .action-pay {
      font-size: 13px;
      color: var(--color-primary);
      font-weight: 500;
    }

    .action-membership {
      font-size: 13px;
      color: var(--color-success);
    }
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 payment 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // ... 其他页面
    'pages/payment/create/index',   // 新增：订单创建页（会员开通）
    'pages/payment/orders/index',   // 新增：订单列表页
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "payment": {
    "openMembership": "开通会员",
    "chooseTier": "选择适合您的会员等级",
    "recommended": "推荐",
    "selectPeriod": "选择订阅周期",
    "save": "省",
    "payable": "应付",
    "wechatPay": "微信支付",
    "paying": "支付中...",
    "createOrderFailed": "订单创建失败",
    "paySuccess": "支付成功",
    "payFailed": "支付失败",
    "payCancelled": "支付已取消",
    "orderNo": "订单号",
    "amount": "金额",
    "createdAt": "创建时间",
    "paidAt": "支付时间",
    "continuePay": "继续支付",
    "membershipActive": "会员已生效",
    "noOrders": "暂无订单",
    "tierMember": "会员版",
    "tierPro": "专业版",
    "tierCoach": "教练版",
    "periodMonthly": "月卡",
    "periodQuarterly": "季卡",
    "periodYearly": "年卡",
    "statusPending": "待支付",
    "statusPaid": "已支付",
    "statusRefunded": "已退款",
    "statusCancelled": "已取消",
    "productMembership": "会员订阅",
    "productAnalysisPack": "分析次数包",
    "status": {
      "all": "全部",
      "pending": "待支付",
      "paid": "已支付",
      "refunded": "已退款",
      "cancelled": "已取消"
    },
    "productType": {
      "membership": "会员订阅",
      "analysis_pack": "分析次数包"
    },
    "featureUnlimitedAnalysis": "无限分析",
    "featureTrainingPlan": "训练方案",
    "feature3DTeaching": "3D教学",
    "featureHistoryCompare": "历史对比",
    "featureMemberAllRights": "会员版全部权益",
    "featureAdvancedAnalysis": "高级分析",
    "featureOpponentModeling": "对手建模",
    "featureMonthlyReport": "月度报告",
    "featureProAllRights": "专业版全部权益",
    "featureStudentManagement": "学员管理",
    "featureBatchAnalysis": "批量分析",
    "featureCoachTools": "教练工具",
    "suffixMonthly": "/月",
    "suffixQuarterly": "/季",
    "suffixYearly": "/年",
    "currencySymbol": "¥"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "payment": {
    "openMembership": "Open Membership",
    "chooseTier": "Choose your membership tier",
    "recommended": "Recommended",
    "selectPeriod": "Select Subscription Period",
    "save": "Save",
    "payable": "Total",
    "wechatPay": "WeChat Pay",
    "paying": "Paying...",
    "createOrderFailed": "Order creation failed",
    "paySuccess": "Payment successful",
    "payFailed": "Payment failed",
    "payCancelled": "Payment cancelled",
    "orderNo": "Order No.",
    "amount": "Amount",
    "createdAt": "Created At",
    "paidAt": "Paid At",
    "continuePay": "Continue Payment",
    "membershipActive": "Membership Active",
    "noOrders": "No orders yet",
    "tierMember": "Member",
    "tierPro": "Pro",
    "tierCoach": "Coach",
    "periodMonthly": "Monthly",
    "periodQuarterly": "Quarterly",
    "periodYearly": "Yearly",
    "statusPending": "Pending",
    "statusPaid": "Paid",
    "statusRefunded": "Refunded",
    "statusCancelled": "Cancelled",
    "productMembership": "Membership",
    "productAnalysisPack": "Analysis Pack",
    "status": {
      "all": "All",
      "pending": "Pending",
      "paid": "Paid",
      "refunded": "Refunded",
      "cancelled": "Cancelled"
    },
    "productType": {
      "membership": "Membership",
      "analysis_pack": "Analysis Pack"
    },
    "featureUnlimitedAnalysis": "Unlimited Analysis",
    "featureTrainingPlan": "Training Plan",
    "feature3DTeaching": "3D Teaching",
    "featureHistoryCompare": "History Compare",
    "featureMemberAllRights": "All Member Rights",
    "featureAdvancedAnalysis": "Advanced Analysis",
    "featureOpponentModeling": "Opponent Modeling",
    "featureMonthlyReport": "Monthly Report",
    "featureProAllRights": "All Pro Rights",
    "featureStudentManagement": "Student Management",
    "featureBatchAnalysis": "Batch Analysis",
    "featureCoachTools": "Coach Tools",
    "suffixMonthly": "/mo",
    "suffixQuarterly": "/qtr",
    "suffixYearly": "/yr",
    "currencySymbol": "$"
  }
}
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 订单创建页：会员等级卡片布局清晰，推荐标签显眼
- [ ] 推荐等级（会员版）使用 `#2A9D8F` 边框高亮
- [ ] 周期选择卡选中时使用主色 `#E63946` 边框 + 淡红背景
- [ ] 底部支付栏固定在页面底部，金额使用主色 `#E63946` 突出显示
- [ ] 订单列表页：状态标签颜色正确（pending=橙 `#F4A261`、paid=绿 `#2A9D8F`、refunded/cancelled=灰）
- [ ] 订单卡片信息排列整齐，金额使用主色高亮
- [ ] 空状态正确显示引导文字
- [ ] Tab 切换时列表正常刷新

### 功能验证
- [ ] 订单创建页：选择等级 → 选择周期 → 金额正确计算
- [ ] 点击"微信支付" → 创建订单 → 调用 `Taro.requestPayment` 拉起微信支付
- [ ] 支付成功 → Toast 提示 → 延迟返回上一页
- [ ] 支付取消 → Toast 提示"支付已取消"
- [ ] 订单列表页：加载 → 显示订单列表
- [ ] 状态 Tab 切换 → 列表筛选
- [ ] WS payment_success 通知 → Toast 提示 + 列表刷新

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 微信支付 **必须** 通过 `Taro.requestPayment` 拉起，**禁止** 自建支付流程
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量（`--color-primary` 等）
- **禁止** 安装新的 npm 包
- 订单列表 **必须** 按状态筛选，**禁止** 在前端做权限过滤（后端已过滤 user_id）
- 支付成功通知 **必须** 通过 WS 事件监听，**禁止** 轮询
- 会员定价 **必须** 与后端 `MEMBERSHIP_PRICING` 一致，**禁止** 前端随意修改价格
