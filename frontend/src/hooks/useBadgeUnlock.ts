/**
 * useBadgeUnlock — WebSocket 徽章解锁监听（09-gamification/frontend.md §8）
 *
 * 后端 BadgeService.check_badges 解锁后经 NotificationService.push_ws_message
 * 推送 {event:'badge_unlocked', data:[{badge_id,name,icon}]}（newly_unlocked
 * 为数组）。
 *
 * FS5-P3 契约同步（与设计文档 §8 样例的差异，以后端实现为准）：
 * - data 为徽章数组而非单对象（后端 push_ws_message(user_id, event_type, newly_unlocked)）
 * - useWebSocket 实际 API 为 options.onMessage（设计样例解构 { onMessage } 不存在）；
 *   连接地址用 buildWsUrl()（Sec-WebSocket-Protocol 子协议认证）
 * 页面级挂载（checkin-calendar / badges / plans detail），弹层由页面渲染。
 */
import { useCallback, useState } from 'react'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import { useGamificationStore } from '@/stores/gamificationStore'
import type { BadgeUnlockedItem } from '@/services/gamification'

export interface UseBadgeUnlockResult {
  /** 弹层是否可见 */
  badgePopupVisible: boolean
  /** 本次解锁的徽章（数组，可能一次解锁多枚） */
  unlockedBadges: BadgeUnlockedItem[]
  /** 关闭弹层 */
  handleBadgePopupClose: () => void
}

export function useBadgeUnlock(): UseBadgeUnlockResult {
  const { fetchBadges } = useGamificationStore()
  const [badgePopupVisible, setBadgePopupVisible] = useState(false)
  const [unlockedBadges, setUnlockedBadges] = useState<BadgeUnlockedItem[]>([])

  const onMessage = useCallback(
    (msg: { event?: string; data?: unknown }) => {
      if (msg.event !== 'badge_unlocked') return
      const data = Array.isArray(msg.data) ? (msg.data as BadgeUnlockedItem[]) : []
      if (data.length === 0) return
      // 弹出徽章解锁弹层，并刷新徽章列表
      setUnlockedBadges(data)
      setBadgePopupVisible(true)
      fetchBadges()
    },
    [fetchBadges]
  )

  // 用户频道连接（子协议认证在 useWebSocket 内处理）
  useWebSocket(buildWsUrl(), { onMessage })

  const handleBadgePopupClose = useCallback(() => {
    setBadgePopupVisible(false)
    setUnlockedBadges([])
  }, [])

  return { badgePopupVisible, unlockedBadges, handleBadgePopupClose }
}

export default useBadgeUnlock
