/**
 * 会员状态管理（10-membership/frontend.md §3）
 * 三份数据独立 loading，互不阻塞；错误静默（页面以 Skeleton/空态兜底）。
 *
 * R-FE-R1 批次B（FE-P2-24）：tiers 加载失败补 tiersError 标志——
 * 支付创建页据此渲染失败空态 + 禁用支付按钮，防 0 元订单提交。
 */
import { create } from 'zustand'
import * as membershipApi from '@/services/membership'
import type { TierListData, CurrentMembershipData, QuotaData } from '@/services/membership'

interface MembershipState {
  /** 等级权益列表（GET /membership/tiers，缓存 1h） */
  tiers: TierListData | null
  /** 当前会员状态（GET /membership/current） */
  current: CurrentMembershipData | null
  /** 今日额度（GET /membership/quota） */
  quota: QuotaData | null
  isLoadingTiers: boolean
  isLoadingCurrent: boolean
  isLoadingQuota: boolean
  /** tiers 拉取失败标志（FE-P2-24：支付页失败空态 + 支付按钮守卫） */
  tiersError: boolean

  // Actions
  fetchTiers: () => Promise<void>
  fetchCurrent: () => Promise<void>
  fetchQuota: () => Promise<void>
  /** 三接口并行刷新（支付成功/会员变更后） */
  refreshAll: () => Promise<void>
}

export const useMembershipStore = create<MembershipState>((set) => ({
  tiers: null,
  current: null,
  quota: null,
  isLoadingTiers: false,
  isLoadingCurrent: false,
  isLoadingQuota: false,
  tiersError: false,

  fetchTiers: async () => {
    set({ isLoadingTiers: true, tiersError: false })
    try {
      const res = await membershipApi.getTiers()
      set({ tiers: res.data.data })
    } catch (error) {
      console.error('fetchTiers failed', error)
      set({ tiersError: true })
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
