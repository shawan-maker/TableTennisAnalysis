# membership 模块 — 前端垂直切片设计

> **模块名称**：`membership`
> **前端目录**：`frontend/src/pages/membership/` + `frontend/src/services/membership.ts` + `frontend/src/stores/membershipStore.ts`
> **定位**：会员中心（等级权益对比表、当前会员状态卡、今日剩余免费额度）
> **依据**：前端需求与界面设计 v2.0 §P5.2、API 详细设计 v1.3 §11

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P5.2 会员中心（Phase 1）
- [ ] 阅读前端设计 v2.0 §1.2 色彩系统（主色 #E63946 / 辅助 #1D3557 / 强调 #F4A261）
- [ ] 阅读本模块的 API 契约（§11.1-11.3，3 个端点）
- [ ] 阅读定价表：免费 ¥0 / 会员 ¥19月¥49季¥168年 / 专业 ¥39月¥99季¥358年 / 教练 ¥99月¥269季¥899年
- [ ] 确认本切片范围：会员中心页（等级权益对比 + 当前状态卡 + 今日额度）

---

## 2. API Service 模块（TypeScript）

```typescript
// frontend/src/services/membership.ts
import request from './request'

/** 会员等级权益 */
export interface TierInfo {
  tier: string
  name: string
  price_monthly: number
  price_quarterly: number
  price_yearly: number
  benefits: string[]
  quota: {
    daily_analysis_limit: number
  }
}

/** 等级列表 */
export interface TierListData {
  tiers: TierInfo[]
}

/** 当前会员状态 */
export interface CurrentMembershipData {
  tier: string
  status: string
  start_at: string | null
  expire_at: string | null
  days_remaining: number
  auto_renew: boolean
}

/** 今日剩余额度 */
export interface QuotaData {
  tier: string
  daily_limit: number
  used_today: number
  remaining: number
  reset_at: string
}

/**
 * 获取会员等级与权益对比。
 */
export function getTiers() {
  return request.get('/membership/tiers')
}

/**
 * 获取当前会员状态。
 */
export function getCurrentMembership() {
  return request.get('/membership/current')
}

/**
 * 获取今日剩余免费分析次数。
 */
export function getQuota() {
  return request.get('/membership/quota')
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/membershipStore.ts
import { create } from 'zustand'
import * as membershipApi from '@/services/membership'
import type {
  TierListData, CurrentMembershipData, QuotaData,
} from '@/services/membership'

interface MembershipState {
  // 等级列表
  tiers: TierListData | null
  // 当前会员状态
  current: CurrentMembershipData | null
  // 今日额度
  quota: QuotaData | null
  // 加载状态
  isLoadingTiers: boolean
  isLoadingCurrent: boolean
  isLoadingQuota: boolean

  // Actions
  fetchTiers: () => Promise<void>
  fetchCurrent: () => Promise<void>
  fetchQuota: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useMembershipStore = create<MembershipState>((set) => ({
  tiers: null,
  current: null,
  quota: null,
  isLoadingTiers: false,
  isLoadingCurrent: false,
  isLoadingQuota: false,

  fetchTiers: async () => {
    set({ isLoadingTiers: true })
    try {
      const res = await membershipApi.getTiers()
      set({ tiers: res.data.data })
    } catch (error) {
      console.error('fetchTiers failed', error)
    } finally {
      set({ isLoadingTiers: false })
    }
  },

  fetchCurrent: async () => {
    set({ isLoadingCurrent: true })
    try {
      const res = await membershipApi.getCurrentMembership()
      set({ current: res.data.data })
    } catch (error) {
      console.error('fetchCurrent failed', error)
    } finally {
      set({ isLoadingCurrent: false })
    }
  },

  fetchQuota: async () => {
    set({ isLoadingQuota: true })
    try {
      const res = await membershipApi.getQuota()
      set({ quota: res.data.data })
    } catch (error) {
      console.error('fetchQuota failed', error)
    } finally {
      set({ isLoadingQuota: false })
    }
  },

  refreshAll: async () => {
    await Promise.all([
      useMembershipStore.getState().fetchTiers(),
      useMembershipStore.getState().fetchCurrent(),
      useMembershipStore.getState().fetchQuota(),
    ])
  },
}))
```

---

## 4. 页面组件（React + TSX + NutUI）

### 4.1 会员中心页

```tsx
// frontend/src/pages/membership/index.tsx
import { useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { NavBar, Button, Skeleton } from '@nutui/nutui-react'
import { useMembershipStore } from '@/stores/membershipStore'
import { useTranslation } from 'react-i18next'
import './membership.scss'

export default function MembershipCenter() {
  const { t, i18n } = useTranslation()
  const {
    tiers, current, quota,
    isLoadingTiers, isLoadingCurrent, isLoadingQuota,
    fetchTiers, fetchCurrent, fetchQuota,
  } = useMembershipStore()

  useEffect(() => {
    fetchTiers()
    fetchCurrent()
    fetchQuota()
  }, [fetchTiers, fetchCurrent, fetchQuota])

  const tierList = tiers?.tiers ?? []
  const currentTier = current?.tier ?? 'free'
  const currentStatus = current?.status ?? 'none'
  const daysRemaining = current?.days_remaining ?? 0

  // 权益对比表表头（取所有权益的并集）
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

  /** 状态显示文案映射 */
  const statusText = (status: string): string => {
    const map: Record<string, string> = {
      active: t('membership.statusActive'),
      expiring_soon: t('membership.statusExpiringSoon'),
      expired: t('membership.statusExpired'),
      grace_period: t('membership.statusGracePeriod'),
      closed: t('membership.statusClosed'),
      none: t('membership.statusNone'),
    }
    return map[status] ?? status
  }

  /** 状态样式类名 */
  const statusClass = (status: string): string => {
    if (['active'].includes(status)) return 'status-active'
    if (['expiring_soon'].includes(status)) return 'status-warning'
    if (['expired', 'closed'].includes(status)) return 'status-danger'
    return 'status-default'
  }

  return (
    <View className="membership-page">
      <NavBar
        title={t('membership.title')}
        onBack={() => Taro.navigateBack()}
      />

      <ScrollView scrollY className="membership-scroll">
        {/* === 当前会员状态卡 === */}
        {isLoadingCurrent ? (
          <View className="current-card">
            <Skeleton rows={3} avatar loading={isLoadingCurrent} />
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
                {new Date(current.expire_at).toLocaleDateString(i18n.language) /* 使用 i18n 当前语言 */}
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

        {/* === 今日剩余免费额度 === */}
        {isLoadingQuota ? (
          <View className="quota-card">
            <Skeleton rows={3} loading={isLoadingQuota} />
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
                    width: `${(quota.used_today / quota.daily_limit) * 100}%`,
                  }}
                />
              </View>
              <Text className="quota-used">
                {t('membership.usedToday', { count: quota.used_today })}
              </Text>
              <Text className="quota-reset">
                {t('membership.resetAt', {
                   time: new Date(quota.reset_at).toLocaleTimeString(i18n.language, { /* 使用 i18n 当前语言 */
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
            <Skeleton rows={5} loading={isLoadingTiers} />
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
                    {tier.price_monthly === 0
                      ? t('membership.free')
                      : t('membership.priceMonthly', { price: (tier.price_monthly / 100).toFixed(0) })}
                  </Text>
                  {tier.price_quarterly > 0 && (
                    <Text className="tier-price-quarterly">
                      {t('membership.priceQuarterly', { price: (tier.price_quarterly / 100).toFixed(0) })}
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
                        : tier.price_monthly === 0
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
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/membership/membership.scss

.membership-page {
  min-height: 100vh;
  background: var(--color-background); // #F8F9FA

  .membership-scroll {
    height: calc(100vh - 44px);
    padding: var(--spacing-md);
  }
}

// === 当前会员状态卡 ===
.current-card {
  background: linear-gradient(135deg, var(--color-secondary) 0%, var(--color-secondary-dark, var(--color-secondary)) 100%);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg) var(--spacing-md);
  margin-bottom: var(--spacing-md);
  color: var(--color-text-inverse);
  position: relative;

  .current-tier-badge {
    display: inline-block;
    background: var(--color-accent); // #F4A261
    color: var(--color-secondary);
    padding: var(--spacing-xs) var(--spacing-sm-md);
    border-radius: var(--radius-md);
    margin-bottom: var(--spacing-sm-md);

    .tier-badge-text {
      font-size: 13px;
      font-weight: bold;
    }
  }

  .current-info {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm-md);
    margin-bottom: var(--spacing-sm-md);

    .current-tier-name {
      font-size: 24px;
      font-weight: bold;
    }

    .current-status {
      padding: var(--spacing-xs) 10px;
      border-radius: var(--radius-md);

      .status-text {
        font-size: 12px;
      }

      &.status-active {
        background: color-mix(in srgb, var(--color-success) 30%, transparent);
        .status-text { color: var(--color-success); }
      }

      &.status-warning {
        background: color-mix(in srgb, var(--color-accent) 30%, transparent);
        .status-text { color: var(--color-accent); }
      }

      &.status-danger {
        background: color-mix(in srgb, var(--color-primary) 30%, transparent);
        .status-text { color: var(--color-primary); }
      }

      &.status-default {
        background: color-mix(in srgb, var(--color-text-secondary) 20%, transparent);
        .status-text { color: var(--color-text-secondary); }
      }
    }
  }

  .current-expire {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    font-size: 13px;
    opacity: 0.9;

    .expire-label {
      opacity: 0.7;
    }

    .expire-date {
      font-weight: 500;
    }

    .expire-remaining {
      margin-left: var(--spacing-sm);
      color: var(--color-accent);
      font-weight: bold;
    }
  }

  .expire-banner {
    margin-top: var(--spacing-md);
    padding: var(--spacing-sm-md);
    background: color-mix(in srgb, var(--color-primary) 20%, transparent);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: space-between;

    .banner-text {
      font-size: 13px;
      color: var(--color-accent);
    }
  }
}

// === 今日额度卡 ===
.quota-card {
  background: var(--color-card); // #FFFFFF
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .quota-header {
    margin-bottom: var(--spacing-sm-md);

    .quota-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
  }

  .quota-body {
    text-align: center;

    .quota-remaining {
      display: flex;
      align-items: baseline;
      justify-content: center;
      gap: var(--spacing-xs);

      .quota-number {
        font-size: 32px;
        font-weight: bold;
        color: var(--color-primary); // #E63946
      }

      .quota-divider {
        font-size: 18px;
        color: var(--color-text-secondary);
      }

      .quota-limit {
        font-size: 18px;
        color: var(--color-text-secondary);
      }
    }

    .quota-label {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }

    .quota-progress {
      width: 100%;
      height: 8px;
      background: var(--color-divider); // #DEE2E6
      border-radius: var(--radius-sm);
      margin: var(--spacing-md) 0 var(--spacing-sm);
      overflow: hidden;

      .quota-progress-bar {
        height: 100%;
        background: var(--color-primary); // #E63946
        border-radius: var(--radius-sm);
        transition: width 0.3s;
      }
    }

    .quota-used {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .quota-reset {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
      opacity: 0.7;
    }
  }
}

// === 等级权益对比表 ===
.tiers-section {
  background: var(--color-card); // #FFFFFF
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .section-title {
    margin-bottom: var(--spacing-sm-md);

    Text {
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
  }

  .tier-table {
    width: 100%;
    overflow-x: auto;

    .table-header,
    .table-row {
      display: flex;
      flex-direction: row;
    }

    .table-header {
      border-bottom: 2px solid var(--color-divider);
      padding-bottom: var(--spacing-sm);
      margin-bottom: var(--spacing-sm);
    }

    .table-row {
      border-bottom: 1px solid var(--color-divider);
      padding: var(--spacing-sm) 0;

      &.action-row {
        padding-top: var(--spacing-md);
        border-bottom: none;
      }
    }

    .table-cell {
      flex: 1;
      text-align: center;
      padding: var(--spacing-xs) var(--spacing-xs); /* P3-fix: 2px→var(--spacing-xs) */

      &.label-cell {
        flex: 0 0 30%;
        text-align: left;

        .header-text,
        .row-label {
          font-size: 12px;
          color: var(--color-text-secondary);
        }

        .row-label {
          font-size: 12px;
        }
      }

      &.tier-cell {
        &.current {
          .tier-name {
            color: var(--color-primary); // #E63946
            font-weight: bold;
          }
        }

        .tier-name {
          display: block;
          font-size: 12px;
          font-weight: 600;
          color: var(--color-text-primary);
        }

        .tier-price {
          display: block;
          font-size: 12px;
          color: var(--color-text-secondary);
          margin-top: var(--spacing-xs);
        }

        .benefit-icon {
          font-size: 13px;

          &.has {
            color: var(--color-success); // #2A9D8F
          }

          &.no {
            color: var(--color-text-secondary);
            opacity: 0.4;
          }
        }

        .subscribe-btn {
          min-width: 60px;
          font-size: 12px;
          padding: 0 var(--spacing-sm);
        }
      }
    }
  }
}

// === 年付优惠提示 ===
.yearly-promo {
  text-align: center;
  padding: var(--spacing-md);

  .promo-text {
    font-size: 12px;
    color: var(--color-accent); // #F4A261
    font-weight: 500;
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 membership 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // ... 其他页面
    'pages/membership/index',    // 新增：会员中心页
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

**页面跳转**：
```typescript
// 我的 Tab → 会员中心
Taro.navigateTo({ url: '/pages/membership/index' })

// 会员中心 → 订阅支付页（点击订阅按钮）
Taro.navigateTo({ url: '/pages/payment/create/index?tier=member' })
```

---

## 7. 常量与 i18n

### 常量

```typescript
// frontend/src/constants/membership.ts

/** 会员等级顺序 */
export const TIER_ORDER = ['free', 'member', 'pro', 'coach'] as const
export type TierName = (typeof TIER_ORDER)[number]

/** 会员状态映射 */
export const MEMBERSHIP_STATUS_MAP: Record<string, {
  color: string
  labelKey: string
}> = {
  active:         { color: 'var(--color-success)',  labelKey: 'membership.statusActive' },
  expiring_soon: { color: 'var(--color-accent)',   labelKey: 'membership.statusExpiringSoon' },
  expired:        { color: 'var(--color-primary)',  labelKey: 'membership.statusExpired' },
  grace_period:   { color: 'var(--color-accent)',   labelKey: 'membership.statusGracePeriod' },
  closed:         { color: 'var(--color-text-secondary)', labelKey: 'membership.statusClosed' },
  none:           { color: 'var(--color-text-secondary)', labelKey: 'membership.statusNone' },
}

/** 定价信息（用于 UI 快速渲染，与后端 tiers 数据一致） */
export const TIER_PRICING = {
  free:   { monthly: 0,    yearly: 0,     labelKey: 'membership.tierFree' },
  member: { monthly: 19,   yearly: 168,   labelKey: 'membership.tierMember' },
  pro:    { monthly: 39,   yearly: 358,   labelKey: 'membership.tierPro' },
  coach:  { monthly: 99,   yearly: 899,   labelKey: 'membership.tierCoach' },
} as const

/** 权益到期后的功能访问状态（用于前端功能入口控制） */
export const EXPIRED_ACCESS_MAP = {
  analysis_reports: 'readonly',   // 历史分析报告只读
  annotated_video: '30days',       // 标注视频 30 天内
  training_plan: 'readonly',       // 训练方案只读
  teaching_3d: 'hidden',           // 3D 教学隐藏
  progress_analysis: 'hidden',     // 进度分析隐藏
  dashboard: 'basic',              // 数据看板基础
} as const
```

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "membership": {
    "title": "会员中心",
    "tierName": {
      "free": "免费版",
      "member": "会员版",
      "pro": "专业版",
      "coach": "教练版"
    },
    "tierFree": "免费",
    "tierMember": "会员版",
    "tierPro": "专业版",
    "tierCoach": "教练版",
    "statusActive": "有效中",
    "statusExpiringSoon": "即将到期",
    "statusExpired": "已到期",
    "statusGracePeriod": "宽限期",
    "statusClosed": "已关闭",
    "statusNone": "免费用户",
    "expireAt": "到期时间",
    "daysRemaining": "剩余{{days}}天",
    "renewNow": "立即续费",
    "expiringSoonBanner": "您的会员将在{{days}}天后到期，请及时续费",
    "todayQuota": "今日免费额度",
    "remainingQuota": "剩余分析次数",
    "usedToday": "今日已用 {{count}} 次",
    "resetAt": "每日 {{time}} 重置",
    "free": "免费",
    "tiersCompare": "会员等级权益对比",
    "benefit": "权益",
    "subscribe": "开通会员",
    "currentTier": "当前等级",
    "yearlyPromo": "年付立省约 2 个月费用，更优惠",
    "priceMonthly": "¥{{price}}/月",
    "priceQuarterly": "¥{{price}}/季"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "membership": {
    "title": "Membership",
    "tierName": {
      "free": "Free",
      "member": "Member",
      "pro": "Pro",
      "coach": "Coach"
    },
    "tierFree": "Free",
    "tierMember": "Member",
    "tierPro": "Pro",
    "tierCoach": "Coach",
    "statusActive": "Active",
    "statusExpiringSoon": "Expiring Soon",
    "statusExpired": "Expired",
    "statusGracePeriod": "Grace Period",
    "statusClosed": "Closed",
    "statusNone": "Free User",
    "expireAt": "Expires",
    "daysRemaining": "{{days}} days remaining",
    "renewNow": "Renew Now",
    "expiringSoonBanner": "Your membership expires in {{days}} days. Renew now to keep your benefits.",
    "todayQuota": "Today's Free Quota",
    "remainingQuota": "Remaining analyses",
    "usedToday": "Used {{count}} today",
    "resetAt": "Resets at {{time}} daily",
    "free": "Free",
    "tiersCompare": "Membership Tier Comparison",
    "benefit": "Benefit",
    "subscribe": "Subscribe",
    "currentTier": "Current",
    "yearlyPromo": "Save ~2 months with annual billing",
    "priceMonthly": "¥{{price}}/mo",
    "priceQuarterly": "¥{{price}}/qtr"
  }
}
```

---

## 8. 权益降级 UI 处理（Hook）

```typescript
// frontend/src/hooks/useMembershipGate.ts
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { useMembershipStore } from '@/stores/membershipStore'
import { EXPIRED_ACCESS_MAP } from '@/constants/membership'
import { useTranslation } from 'react-i18next'

/**
 * 会员权益门控 Hook。
 * 用于在功能入口判断当前用户是否有权限访问。
 * 
 * 用法：
 * const { canAccess, showUpgradePrompt } = useMembershipGate('progress_analysis')
 * if (!canAccess) { showUpgradePrompt(); return }
 */
export function useMembershipGate(feature: keyof typeof EXPIRED_ACCESS_MAP) {
  const { t } = useTranslation()
  const { current, fetchCurrent } = useMembershipStore()
  const [canAccess, setCanAccess] = useState(true)
  const [upgradeVisible, setUpgradeVisible] = useState(false)

  useEffect(() => {
    fetchCurrent()
  }, [fetchCurrent])

  useEffect(() => {
    const tier = current?.tier ?? 'free'
    const status = current?.status ?? 'none'

    if (tier === 'free' || status === 'expired' || status === 'closed') {
      const accessLevel = EXPIRED_ACCESS_MAP[feature]
      // hidden 功能不可访问
      // readonly 功能可访问但不可操作
      // basic / 30days 功能可访问
      setCanAccess(accessLevel !== 'hidden')
    } else {
      setCanAccess(true)
    }
  }, [current, feature])

  /** 显示升级提示弹窗（使用 NutUI Popup position="bottom"） */
  const showUpgradePrompt = () => {
    setUpgradeVisible(true)
  }

  /** 升级确认 → 跳转会员中心 */
  const handleUpgradeConfirm = () => {
    setUpgradeVisible(false)
    Taro.navigateTo({ url: '/pages/membership/index' })
  }

  /** 升级取消 */
  const handleUpgradeCancel = () => {
    setUpgradeVisible(false)
  }

  return {
    canAccess,
    showUpgradePrompt,
    upgradeVisible,
    handleUpgradeConfirm,
    handleUpgradeCancel,
  }
}
```

---

## 9. 验证清单

### 构建验证
```bash
cd frontend && npm run build:weapp
```

### 视觉验证
- [ ] 当前会员状态卡：深蓝渐变背景（#1D3557），等级徽章橙色（#F4A261）
- [ ] 状态标签颜色正确：active=绿色 / expiring_soon=橙色 / expired=红色
- [ ] 免费用户显示"今日免费额度"卡，已用/剩余以红色数字突出（#E63946）
- [ ] 额度进度条颜色为红色（#E63946），已用部分填充
- [ ] 权益对比表：权益行使用绿色 ✓ 和灰色 — 标记有无
- [ ] 当前等级列高亮红色（#E63946）
- [ ] 订阅按钮使用主色（#E63946）
- [ ] 到期提醒 banner 使用红橙色调
- [ ] 空状态正确显示引导文字

### 功能验证
- [ ] 进入会员中心页：自动加载等级列表 + 当前状态 + 今日额度
- [ ] 权益对比表正确渲染所有等级和权益行
- [ ] 点击"开通会员"按钮跳转到支付页
- [ ] 免费用户额度用完后，进入视频分析时显示升级提示
- [ ] 到期会员的功能入口被隐藏（如 3D 教学、进度分析）
- [ ] WebSocket 收到 membership_downgrade 事件后刷新状态

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量（`--color-primary` / `--color-secondary` / `--color-accent` / `--color-success`），**禁止** 硬编码色值
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- 会员等级定价 **必须** 与后端 `MembershipTier` 表一致（免费 ¥0 / 会员 ¥19月¥49季¥168年 / 专业 ¥39月¥99季¥358年 / 教练 ¥99月¥269季¥899年）
- 权益降级 **必须** 使用 `useMembershipGate` Hook 统一控制功能入口可见性
- 额度进度条 **必须** 实时计算（used_today / daily_limit × 100%）
- 到期提醒 banner **必须** 在 `expiring_soon` 状态下自动显示
