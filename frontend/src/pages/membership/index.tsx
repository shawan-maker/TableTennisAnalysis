/**
 * 会员中心页（10-membership/frontend.md §4.1）
 * 当前状态卡 + 免费额度卡 + 等级权益对比表 + 支付成功权益即时刷新。
 *
 * FS6-P3 契约同步（以后端 TierBrief 为准）：
 * - 定价字段 price_monthly_cents / price_quarterly_cents / price_yearly_cents
 *   （设计样例缺 _cents 后缀）
 * - 权益行直接渲染后端 tiers[].benefits 中文字符串（后端种子，en 布局下保持原文，
 *   与设计 §4.1 allBenefits 并集算法一致）
 * - NavBar 未采用：工程先例为原生导航栏（index.config.ts 静态标题，FS1-FS5 同构）
 * - 状态文案/颜色映射走 constants/membership.ts MEMBERSHIP_STATUS_MAP（§7 常量）
 */
import { useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Button, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useMembershipStore } from '@/stores/membershipStore'
import { usePaymentNotify } from '@/hooks/usePaymentNotify'
import { MEMBERSHIP_STATUS_MAP } from '@/constants/membership'
import './membership.scss'

export default function MembershipCenter() {
  const { t, i18n } = useTranslation()
  const {
    tiers, current, quota,
    isLoadingTiers, isLoadingCurrent, isLoadingQuota,
    fetchTiers, fetchCurrent, fetchQuota, refreshAll,
  } = useMembershipStore()

  useEffect(() => {
    fetchTiers()
    fetchCurrent()
    fetchQuota()
  }, [fetchTiers, fetchCurrent, fetchQuota])

  // 支付成功 WS → 权益即时刷新（实施计划 FS6「支付 WS」行）
  usePaymentNotify(() => {
    refreshAll()
  })

  const tierList = tiers?.tiers ?? []
  const currentTier = current?.tier ?? 'free'
  const currentStatus = current?.status ?? 'none'
  const daysRemaining = current?.days_remaining ?? 0

  // 权益对比表行（取所有等级权益的并集）
  const allBenefits = new Set<string>()
  tierList.forEach((tier) => {
    tier.benefits.forEach((b) => allBenefits.add(b))
  })
  const benefitRows = Array.from(allBenefits)

  /** 跳转到支付页面 */
  const handleSubscribe = (tier: string) => {
    if (tier === 'free') return
    Taro.navigateTo({ url: `/pages/payment/create/index?tier=${tier}` })
  }

  /** 状态显示文案（MEMBERSHIP_STATUS_MAP，§7 常量） */
  const statusText = (status: string): string => {
    const config = MEMBERSHIP_STATUS_MAP[status]
    return config ? t(config.labelKey) : status
  }

  /** 状态样式类名 */
  const statusClass = (status: string): string => {
    if (status === 'active') return 'status-active'
    if (status === 'expiring_soon') return 'status-warning'
    if (status === 'expired' || status === 'closed') return 'status-danger'
    return 'status-default'
  }

  return (
    <ScrollView scrollY className="membership-page">
      {/* === 当前会员状态卡 === */}
      {isLoadingCurrent ? (
        <View className="current-card">
          <Skeleton rows={3} visible={isLoadingCurrent} />
        </View>
      ) : (
      <View className="current-card">
        <View className="current-tier-badge">
          <Text className="tier-badge-text">
            {currentTier.toUpperCase()}
          </Text>
        </View>
        <View className="current-info">
          <Text className="current-tier-name">
            {t(`membership.tierName.${currentTier}`)}
          </Text>
          <View className={`current-status ${statusClass(currentStatus)}`}>
            <Text className="status-text">{statusText(currentStatus)}</Text>
          </View>
        </View>
        {currentTier !== 'free' && current?.expire_at && (
          <View className="current-expire">
            <Text className="expire-label">{t('membership.expireAt')}</Text>
            <Text className="expire-date">
              {new Date(current.expire_at).toLocaleDateString(i18n.language)}
            </Text>
            <Text className="expire-remaining">
              {t('membership.daysRemaining', { days: daysRemaining })}
            </Text>
          </View>
        )}
        {/* 到期提醒 banner */}
        {currentStatus === 'expiring_soon' && (
          <View className="expire-banner">
            <Text className="banner-text">
              {t('membership.expiringSoonBanner', { days: daysRemaining })}
            </Text>
            <Button
              size="small"
              type="primary"
              onClick={() => handleSubscribe(currentTier)}
            >
              {t('membership.renewNow')}
            </Button>
          </View>
        )}
      </View>
      )}

      {/* === 今日剩余免费额度（免费用户）=== */}
      {isLoadingQuota ? (
        <View className="quota-card">
          <Skeleton rows={3} visible={isLoadingQuota} />
        </View>
      ) : currentTier === 'free' && quota ? (
        <View className="quota-card">
          <View className="quota-header">
            <Text className="quota-title">{t('membership.todayQuota')}</Text>
          </View>
          <View className="quota-body">
            <View className="quota-remaining">
              <Text className="quota-number">{quota.remaining}</Text>
              <Text className="quota-divider">/</Text>
              <Text className="quota-limit">{quota.daily_limit}</Text>
            </View>
            <Text className="quota-label">{t('membership.remainingQuota')}</Text>
            <View className="quota-progress">
              <View
                className="quota-progress-bar"
                style={{
                  width: `${quota.daily_limit > 0 ? (quota.used_today / quota.daily_limit) * 100 : 0}%`,
                }}
              />
            </View>
            <Text className="quota-used">
              {t('membership.usedToday', { count: quota.used_today })}
            </Text>
            <Text className="quota-reset">
              {t('membership.resetAt', {
                 time: new Date(quota.reset_at).toLocaleTimeString(i18n.language, {
                   hour: '2-digit',
                   minute: '2-digit',
                 }),
              })}
            </Text>
          </View>
        </View>
      ) : null}

      {/* === 等级权益对比表 === */}
      {isLoadingTiers ? (
        <View className="tiers-section">
          <Skeleton rows={5} visible={isLoadingTiers} />
        </View>
      ) : (
      <View className="tiers-section">
        <View className="section-title">
          <Text>{t('membership.tiersCompare')}</Text>
        </View>

        {/* 对比表 */}
        <View className="tier-table">
          {/* 表头 */}
          <View className="table-header">
            <View className="table-cell label-cell">
              <Text className="header-text">{t('membership.benefit')}</Text>
            </View>
            {tierList.map((tier) => (
              <View
                key={tier.tier}
                className={`table-cell tier-cell ${tier.tier === currentTier ? 'current' : ''}`}
              >
                <Text className="tier-name">{tier.name}</Text>
                <Text className="tier-price">
                  {tier.price_monthly_cents === 0
                    ? t('membership.free')
                    : t('membership.priceMonthly', { price: (tier.price_monthly_cents / 100).toFixed(0) })}
                </Text>
                {tier.price_quarterly_cents > 0 && (
                  <Text className="tier-price-quarterly">
                    {t('membership.priceQuarterly', { price: (tier.price_quarterly_cents / 100).toFixed(0) })}
                  </Text>
                )}
              </View>
            ))}
          </View>

          {/* 权益行 */}
          {benefitRows.map((benefit) => (
            <View key={benefit} className="table-row">
              <View className="table-cell label-cell">
                <Text className="row-label">{benefit}</Text>
              </View>
              {tierList.map((tier) => {
                const hasBenefit = tier.benefits.includes(benefit)
                return (
                  <View key={tier.tier} className="table-cell tier-cell">
                    <Text className={`benefit-icon ${hasBenefit ? 'has' : 'no'}`}>
                      {hasBenefit ? '✓' : '—'}
                    </Text>
                  </View>
                )
              })}
            </View>
          ))}

          {/* 操作按钮行 */}
          <View className="table-row action-row">
            <View className="table-cell label-cell" />
            {tierList.map((tier) => {
              const isCurrent = tier.tier === currentTier
              return (
                <View key={tier.tier} className="table-cell tier-cell">
                  <Button
                    size="small"
                    type={isCurrent ? 'default' : 'primary'}
                    disabled={isCurrent}
                    onClick={() => handleSubscribe(tier.tier)}
                    className="subscribe-btn"
                  >
                    {isCurrent
                      ? t('membership.currentTier')
                      : tier.price_monthly_cents === 0
                        ? t('membership.currentTier')
                        : t('membership.subscribe')}
                  </Button>
                </View>
              )
            })}
          </View>
        </View>
      </View>
      )}

      {/* === 年付优惠提示 === */}
      <View className="yearly-promo">
        <Text className="promo-text">
          {t('membership.yearlyPromo')}
        </Text>
      </View>
    </ScrollView>
  )
}
