/**
 * 订单创建页（11-payment/frontend.md §4.1）
 * 等级选择 + 周期选择 + 应付金额 + 微信 JSAPI 支付拉起。
 *
 * FS6-P3 契约同步（与设计样例差异，按工程现实落地）：
 * - 定价不从硬编码 MEMBERSHIP_TIERS.pricing（元）取，改从后端
 *   GET /membership/tiers（price_*_cents 分）动态匹配（反幻觉：单一权威源）
 * - NutUI 受控 Toast 样例改 Taro.showToast（FS5 先例）
 * - Toast Icon 组件样例改文本 ✓（工程先例：dashboard 趋势符号）
 * - 支付成功后新增 pollOrderStatus 降级轮询（实施计划「降级路径」：
 *   payment_success WS 未达/微信回调延迟时轮询确认 status==='paid'，
 *   成功后刷新会员权益与订单列表）
 * - create 页不挂 usePaymentNotify（Toast 唯一出口在 handlePay，
 *   避免会员中心→支付页页面栈共存双 Toast；权益刷新走轮询兜底 + 会员页 WS）
 */
import { useState, useCallback, useEffect, useMemo } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, Radio, ScrollView } from '@tarojs/components'
import { Button, Tag, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { usePaymentStore } from '@/stores/paymentStore'
import { useMembershipStore } from '@/stores/membershipStore'
import { formatAmount } from '@/utils/payment'
import './create.scss'

/** 会员等级展示配置（定价从后端 tiers 动态取，此处只承载文案/配色） */
const MEMBERSHIP_TIERS = [
  {
    tier: 'member',
    nameKey: 'membership.tierName.member',
    featureKeys: ['payment.featureUnlimitedAnalysis', 'payment.featureTrainingPlan', 'payment.feature3DTeaching', 'payment.featureHistoryCompare'],
    recommended: true,
    color: 'var(--color-success)',
  },
  {
    tier: 'pro',
    nameKey: 'membership.tierName.pro',
    featureKeys: ['payment.featureMemberAllRights', 'payment.featureAdvancedAnalysis', 'payment.featureOpponentModeling', 'payment.featureMonthlyReport'],
    recommended: false,
    color: 'var(--color-secondary)',
  },
  {
    tier: 'coach',
    nameKey: 'membership.tierName.coach',
    featureKeys: ['payment.featureProAllRights', 'payment.featureStudentManagement', 'payment.featureBatchAnalysis', 'payment.featureCoachTools'],
    recommended: false,
    color: 'var(--color-accent)',
  },
] as const

/** 周期配置 */
const PERIOD_OPTIONS = [
  { value: 'monthly', labelKey: 'payment.periodMonthly', suffixKey: 'payment.suffixMonthly' },
  { value: 'quarterly', labelKey: 'payment.periodQuarterly', suffixKey: 'payment.suffixQuarterly' },
  { value: 'yearly', labelKey: 'payment.periodYearly', suffixKey: 'payment.suffixYearly' },
] as const

export default function CreateOrder() {
  const { t } = useTranslation()
  const router = useRouter()
  const { createOrder, requestWechatPay, pollOrderStatus, loading, paying } = usePaymentStore()
  const { tiers, isLoadingTiers, fetchTiers } = useMembershipStore()
  const [selectedTier, setSelectedTier] = useState('member')
  const [selectedPeriod, setSelectedPeriod] = useState('monthly')

  // 会员中心带入等级（?tier=member/pro/coach）
  useEffect(() => {
    const tier = router.params?.tier
    if (tier && MEMBERSHIP_TIERS.some((x) => x.tier === tier)) {
      setSelectedTier(tier)
    }
  }, [router.params?.tier])

  // 定价从后端 tiers 动态取（单一权威源）
  useEffect(() => {
    fetchTiers()
  }, [fetchTiers])

  /** 后端分定价匹配（FS6-P3：price_*_cents） */
  const backendPricing = useMemo(() => {
    const tierData = tiers?.tiers.find((x) => x.tier === selectedTier)
    return {
      monthly: tierData?.price_monthly_cents ?? 0,
      quarterly: tierData?.price_quarterly_cents ?? 0,
      yearly: tierData?.price_yearly_cents ?? 0,
    }
  }, [tiers, selectedTier])

  const amountCents = backendPricing[selectedPeriod as keyof typeof backendPricing]

  /** 计算节省金额（后端价） */
  const calcSavings = (period: string): number => {
    if (period === 'quarterly') return backendPricing.monthly * 3 - backendPricing.quarterly
    if (period === 'yearly') return backendPricing.monthly * 12 - backendPricing.yearly
    return 0
  }

  /** 提交订单 → 微信支付 → 降级轮询确认 */
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
        Taro.showToast({ title: t('payment.createOrderFailed'), icon: 'none' })
        return
      }

      // 2. 拉起微信支付（JSAPI）
      const paySuccess = await requestWechatPay(result.payment_params)

      if (paySuccess) {
        Taro.showToast({ title: t('payment.paySuccess'), icon: 'success' })
        // 3. 降级轮询兜底（payment_success WS 未达/微信回调延迟）：
        //    确认转 paid 后刷新会员权益与订单列表
        pollOrderStatus(result.order_id).then((confirmed) => {
          if (confirmed) {
            useMembershipStore.getState().refreshAll()
            usePaymentStore.getState().fetchOrders()
          }
        })
        // 支付成功后延迟返回
        setTimeout(() => {
          Taro.navigateBack()
        }, 1500)
      } else {
        Taro.showToast({ title: t('payment.payCancelled'), icon: 'none' })
        // 刷新订单列表（订单已创建但未支付）
        usePaymentStore.getState().fetchOrders()
      }
    } catch (err: any) {
      Taro.showToast({ title: err?.message || t('payment.payFailed'), icon: 'none' })
    }
  }, [selectedTier, selectedPeriod, createOrder, requestWechatPay, pollOrderStatus, t])

  return (
    <ScrollView scrollY className="payment-create">
      {/* 标题 */}
      <View className="page-header">
        <Text className="page-title">{t('payment.openMembership')}</Text>
        <Text className="page-subtitle">{t('payment.chooseTier')}</Text>
      </View>

      {/* 会员等级选择 */}
      {isLoadingTiers ? (
        <View className="tier-list">
          <Skeleton rows={4} visible={isLoadingTiers} />
        </View>
      ) : (
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
              {tier.featureKeys.map((f) => (
                <Text key={f} className="feature-item">✓ {t(f)}</Text>
              ))}
            </View>
          </View>
        ))}
      </View>
      )}

      {/* 周期选择 */}
      <View className="period-section">
        <Text className="section-title">{t('payment.selectPeriod')}</Text>
        <View className="period-list">
          {PERIOD_OPTIONS.map((opt) => {
            const price = backendPricing[opt.value as keyof typeof backendPricing]
            const periodSavings = calcSavings(opt.value)
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
    </ScrollView>
  )
}
