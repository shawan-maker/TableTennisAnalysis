/**
 * useMembershipGate — 会员权益门控 Hook（10-membership/frontend.md §8）
 *
 * 功能入口统一控制：free / expired / closed 状态下按 EXPIRED_ACCESS_MAP
 * 判定 canAccess（hidden 不可访问 / readonly·basic·30days 可访问）。
 *
 * 用法：
 * const { canAccess, showUpgradePrompt, upgradeVisible,
 *         handleUpgradeConfirm, handleUpgradeCancel } = useMembershipGate('progress_analysis')
 * if (!canAccess) { showUpgradePrompt(); return }
 *
 * 升级弹层（Popup position="bottom"）由消费页面渲染（设计 §8：Hook 只管
 * visible 与 handlers；文案 key membership.upgradeTitle 等）。
 */
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { useMembershipStore } from '@/stores/membershipStore'
import { EXPIRED_ACCESS_MAP } from '@/constants/membership'
import type { MembershipFeature } from '@/constants/membership'

/**
 * 权益门控判定纯函数（§8 逻辑核心，供 Hook 与测试共用）。
 * free / expired / closed 状态下按 EXPIRED_ACCESS_MAP 判定：
 * hidden → 不可访问；readonly / basic / 30days → 可访问。
 */
export function computeMembershipAccess(
  tier: string,
  status: string,
  feature: MembershipFeature
): boolean {
  if (tier === 'free' || status === 'expired' || status === 'closed') {
    const accessLevel = EXPIRED_ACCESS_MAP[feature]
    return accessLevel !== 'hidden'
  }
  return true
}

export interface UseMembershipGateResult {
  canAccess: boolean
  showUpgradePrompt: () => void
  upgradeVisible: boolean
  handleUpgradeConfirm: () => void
  handleUpgradeCancel: () => void
}

export function useMembershipGate(feature: MembershipFeature): UseMembershipGateResult {
  const current = useMembershipStore((s) => s.current)
  const fetchCurrent = useMembershipStore((s) => s.fetchCurrent)
  const [canAccess, setCanAccess] = useState(true)
  const [upgradeVisible, setUpgradeVisible] = useState(false)

  useEffect(() => {
    fetchCurrent()
  }, [fetchCurrent])

  useEffect(() => {
    const tier = current?.tier ?? 'free'
    const status = current?.status ?? 'none'
    setCanAccess(computeMembershipAccess(tier, status, feature))
  }, [current, feature])

  /** 显示升级提示弹窗（使用 NutUI Popup position="bottom"，页面渲染） */
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

export default useMembershipGate
