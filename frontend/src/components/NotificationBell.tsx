/**
 * 通知铃铛组件（12-notification/frontend.md §5）
 * 功能：未读计数红点、点击跳转通知列表、tabBar 角标同步。
 *
 * FS6-P3（挂载点 + 角标扩展，实施计划 FS6「WS 角标」行）：
 * - 设计 §5 挂首页顶部——首页聚合归 FS7，本期挂 user/profile（我的 Tab）页头
 * - WS 内置事件（notification/sync/export_completed）在 useWebSocket 单例内
 *   单次消化，铃铛仅需挂载连接 + 订阅 unreadCount 渲染
 * - tabBar 角标：unreadCount 变化同步到「我的」Tab（USER_TAB_INDEX=4），
 *   >0 显示数字（>99 截断 99+），归零移除
 */
import { FC, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { useNotificationStore } from '@/stores/notificationStore'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import { USER_TAB_INDEX } from '@/constants/membership'
import './NotificationBell.scss'

interface NotificationBellProps {
  /** 点击跳转路径 */
  redirectTo?: string
}

/**
 * 通知铃铛——显示在页头。
 * 功能：未读计数红点、点击跳转通知列表、tabBar 角标同步。
 */
const NotificationBell: FC<NotificationBellProps> = ({
  redirectTo = '/pages/notification/list/index',
}) => {
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount)

  // 用户频道连接（通知域事件在单例内消化，此处仅建立共享连接）
  useWebSocket(buildWsUrl())

  useEffect(() => {
    fetchUnreadCount()
  }, [fetchUnreadCount])

  // tabBar 角标同步（「我的」Tab）
  useEffect(() => {
    if (unreadCount > 0) {
      const text = unreadCount > 99 ? '99+' : String(unreadCount)
      Taro.setTabBarBadge({ index: USER_TAB_INDEX, text }).catch(() => {
        // 非 Tab 场景（H5/测试环境）静默
      })
    } else {
      Taro.removeTabBarBadge({ index: USER_TAB_INDEX }).catch(() => {
        // 同上
      })
    }
  }, [unreadCount])

  const handleClick = () => {
    Taro.navigateTo({ url: redirectTo })
  }

  return (
    <View className="notif-bell" onClick={handleClick}>
      <Text className="notif-bell-icon">🔔</Text>
      {unreadCount > 0 && (
        <View className="notif-bell-badge">
          <Text className="notif-bell-badge-text">
            {unreadCount > 99 ? '99+' : unreadCount}
          </Text>
        </View>
      )}
    </View>
  )
}

export default NotificationBell
