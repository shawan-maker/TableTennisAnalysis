/**
 * 通知列表页（12-notification/frontend.md §6）
 * 分页加载 + 未读/已读筛选 + 下拉刷新 + 上拉加载 + 标记已读 + WS 实时插入。
 *
 * FS6-P3 契约同步（与设计样例差异，按工程现实落地）：
 * - 实施计划要求「未读/已读筛选」而设计 §6 无筛选 UI → 增加 all/unread/read
 *   Tabs（后端 is_read 参数支持：unread→is_read:false / read→is_read:true）
 * - Empty 组件按 NutUI 2.7.14 真实 API 用 title（样例 description 不存在）
 * - 挂 useWebSocket 共享连接：通知域事件（notification/sync/export_completed）
 *   在单例内消化直达 store，列表自动顶部插入；防 deep link 直达时无连接
 */
import { useEffect, useState, useCallback } from 'react'
import Taro, { usePullDownRefresh, useReachBottom } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Button, Tabs, Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useNotificationStore } from '@/stores/notificationStore'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import type { NotificationItem } from '@/services/notification'
import './list.scss'

/** 获取通知图标 */
const getNotifIcon = (type: string): string => {
  const iconMap: Record<string, string> = {
    analysis_complete: '📊',
    payment_success: '💳',
    training_reminder: '🏓',
    score_update: '🏆',
    badge_unlocked: '🎖️',
  }
  return iconMap[type] || '📢'
}

export default function NotificationList() {
  const { t, i18n } = useTranslation()
  const {
    notifications,
    isLoading,
    hasMore,
    unreadCount,
    fetchNotifications,
    fetchUnreadCount,
    markAsRead,
    markAllAsRead,
    reset,
  } = useNotificationStore()
  const [activeTab, setActiveTab] = useState('all')

  // 共享 WS 连接（通知域事件在单例内消化直达 store）
  useWebSocket(buildWsUrl())

  useEffect(() => {
    const filter = activeTab === 'all' ? undefined : { is_read: activeTab === 'read' }
    fetchNotifications(true, filter)
    fetchUnreadCount()
  }, [activeTab, fetchNotifications, fetchUnreadCount])

  // 卸载时重置分页状态
  useEffect(() => {
    return () => {
      reset()
    }
  }, [reset])

  // 下拉刷新
  usePullDownRefresh(() => {
    const filter = activeTab === 'all' ? undefined : { is_read: activeTab === 'read' }
    Promise.all([
      fetchNotifications(true, filter),
      fetchUnreadCount(),
    ]).then(() => {
      Taro.stopPullDownRefresh()
    })
  })

  // 上拉加载更多
  useReachBottom(() => {
    const filter = activeTab === 'all' ? undefined : { is_read: activeTab === 'read' }
    fetchNotifications(false, filter)
  })

  /** 处理通知点击：未读标记已读 + 按 extra_data.action_url 跳转 */
  const handleNotificationClick = useCallback(
    (item: NotificationItem) => {
      if (!item.is_read) {
        markAsRead([item.id])
      }
      if (item.extra_data?.action_url) {
        Taro.navigateTo({ url: item.extra_data.action_url })
      }
    },
    [markAsRead]
  )

  /** 格式化相对时间 */
  const formatTime = (iso: string) => {
    const date = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)
    if (minutes < 1) return t('common.justNow')
    if (minutes < 60) return `${minutes}${t('common.minutesAgo')}`
    if (hours < 24) return `${hours}${t('common.hoursAgo')}`
    if (days < 7) return `${days}${t('common.daysAgo')}`
    return date.toLocaleDateString(i18n.language)
  }

  return (
    <View className="notification-list">
      {/* 筛选 Tab（实施计划 FS6：未读/已读筛选） */}
      <Tabs value={activeTab} onChange={(val) => setActiveTab(val as string)}>
        <Tabs.TabPane title={t('notification.filterAll')} value="all" />
        <Tabs.TabPane title={t('notification.filterUnread')} value="unread" />
        <Tabs.TabPane title={t('notification.filterRead')} value="read" />
      </Tabs>

      {/* 顶部操作栏 */}
      <View className="notification-header">
        <Text className="notification-header-title">
          {t('notification.title')}
        </Text>
        {unreadCount > 0 && (
          <Button
            size="small"
            type="primary"
            shape="round"
            onClick={() => markAllAsRead()}
            loading={isLoading}
          >
            {t('notification.markAllRead')}
          </Button>
        )}
      </View>

      {/* 通知列表 */}
      <ScrollView scrollY className="notification-scroll">
        {notifications.length === 0 && !isLoading ? (
          <Empty title={t('notification.empty')} />
        ) : (
          <View className="notification-items">
            {notifications.map((item) => (
              <Cell
                key={item.id}
                className={`notification-item ${!item.is_read ? 'unread' : ''}`}
                onClick={() => handleNotificationClick(item)}
              >
                <View className="notification-item-inner">
                  <View className="notification-item-icon">
                    <Text className="notification-item-icon-text">
                      {getNotifIcon(item.type)}
                    </Text>
                    {!item.is_read && <View className="unread-dot" />}
                  </View>
                  <View className="notification-item-content">
                    <Text className="notification-item-title">
                      {item.title}
                    </Text>
                    {item.content && (
                      <Text className="notification-item-desc">
                        {item.content}
                      </Text>
                    )}
                    <Text className="notification-item-time">
                      {formatTime(item.created_at)}
                    </Text>
                  </View>
                </View>
              </Cell>
            ))}
          </View>
        )}

        {/* 加载更多 */}
        {isLoading && (
          <View className="notification-loading">
            <Skeleton rows={2} visible={isLoading} />
          </View>
        )}
        {!hasMore && notifications.length > 0 && (
          <View className="notification-end">
            <Text className="notification-end-text">
              {t('common.noMore')}
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  )
}
