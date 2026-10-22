# notification 模块 — 前端垂直切片设计

> **模块名称**：`notification`
> **前端目录**：`frontend/src/pages/notification/` + `frontend/src/services/notification.ts` + `frontend/src/stores/notificationStore.ts` + `frontend/src/hooks/useWebSocket.ts`
> **定位**：通知列表页（分页+未读标记+标记已读）、通知中心（铃铛图标+未读计数）、WebSocket 实时连接管理
> **依据**：前端需求与界面设计 v2.0、API 详细设计 v1.3 §13-14

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0（L1 首页通知铃铛、L1 个人→通知列表）
- [ ] 阅读本模块的 API 契约（§13.1-13.3，3 个 REST 端点 + §14 WebSocket）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：通知列表页 + 通知中心铃铛组件 + WebSocket Hook + notificationStore

---

## 2. API Service 模块

```typescript
// frontend/src/services/notification.ts
import request from './request'

/** 通知类型 */
export interface NotificationItem {
  id: number
  type: string
  title: string
  content: string
  is_read: boolean
  extra_data: Record<string, any> | null
  created_at: string
}

/** 通知列表查询参数 */
export interface NotificationListParams {
  is_read?: boolean
  type?: string
  page?: number
  page_size?: number
}

/**
 * 获取通知列表（分页）。
 * @param params - 查询参数
 */
export function listNotifications(params: NotificationListParams = {}) {
  return request.get('/notification/list', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 批量标记已读。
 * @param notification_ids - 通知 ID 列表
 */
export function markRead(notification_ids: number[]) {
  return request.post('/notification/read', { notification_ids })
}

/**
 * 微信订阅消息授权。
 * @param template_ids - 模板 ID 列表
 */
export function subscribeTemplates(template_ids: string[]) {
  return request.post('/notification/subscribe', { template_ids })
}

/**
 * 获取未读通知数量。
 */
export function getUnreadCount() {
  return request.get('/notification/unread-count')
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/notificationStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as notifApi from '@/services/notification'
import type { NotificationItem } from '@/services/notification'

interface NotificationState {
  /** 未读通知数量 */
  unreadCount: number
  /** 通知列表 */
  notifications: NotificationItem[]
  /** 是否有更多数据 */
  hasMore: boolean
  /** 当前页码 */
  currentPage: number
  /** 是否加载中 */
  isLoading: boolean
  /** WebSocket 连接状态 */
  wsConnected: boolean

  // Actions
  fetchUnreadCount: () => Promise<void>
  fetchNotifications: (reset?: boolean, filter?: { is_read?: boolean }) => Promise<void>
  markAsRead: (ids: number[]) => Promise<void>
  markAllAsRead: () => Promise<void>
  setWsConnected: (connected: boolean) => void
  addNotification: (item: NotificationItem) => void
  reset: () => void
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,
  notifications: [],
  hasMore: true,
  currentPage: 1,
  isLoading: false,
  wsConnected: false,

  fetchUnreadCount: async () => {
    try {
      const res = await notifApi.getUnreadCount()
      set({ unreadCount: res.data.data.unread_count })
    } catch {
      // 静默失败
    }
  },

  fetchNotifications: async (reset = false, filter) => {
    const { currentPage, hasMore, isLoading } = get()
    if (isLoading || (!reset && !hasMore)) return

    const page = reset ? 1 : currentPage + 1
    set({ isLoading: true })
    try {
      const res = await notifApi.listNotifications({
        ...filter,
        page,
        page_size: 20,
      })
      const data = res.data.data
      set({
        notifications: reset
          ? data.items
          : [...get().notifications, ...data.items],
        hasMore: data.items.length >= 20,
        currentPage: page,
      })
    } catch (error) {
      console.error('fetchNotifications failed', error)
    } finally {
      set({ isLoading: false })
    }
  },

  markAsRead: async (ids) => {
    try {
      const res = await notifApi.markRead(ids)
      const updated = res.data.data.updated_count
      // 更新本地列表状态
      set({
        notifications: get().notifications.map((n) =>
          ids.includes(n.id) ? { ...n, is_read: true } : n
        ),
        unreadCount: Math.max(0, get().unreadCount - updated),
      })
    } catch (error) {
      console.error('markAsRead failed', error)
    }
  },

  markAllAsRead: async () => {
    try {
      const unreadIds = get()
        .notifications.filter((n) => !n.is_read)
        .map((n) => n.id)
      if (unreadIds.length === 0) return
      await get().markAsRead(unreadIds)
    } catch (error) {
      console.error('markAllAsRead failed', error)
    }
  },

  setWsConnected: (connected) => set({ wsConnected: connected }),

  addNotification: (item) => {
    set({
      notifications: [item, ...get().notifications],
      unreadCount: get().unreadCount + 1,
    })
  },

  reset: () => {
    set({
      notifications: [],
      hasMore: true,
      currentPage: 1,
    })
  },
}))
```

---

## 4. WebSocket Hook

```typescript
// frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback, useState } from 'react'
import Taro from '@tarojs/taro'
import { useAuthStore } from '@/stores/authStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { NotificationItem } from '@/services/notification'

/** 重连退避序列 */
const BACKOFF = [1000, 2000, 4000, 8000, 16000]
const MAX_RETRIES = 5
const HEARTBEAT_INTERVAL = 30000 // 30s

// ── 模块级单例：多个 useWebSocket 调用共享同一连接 ──
let sharedSocket: Taro.SocketTask | null = null
let connectionCount = 0
const sharedListeners = new Set<Function>()
let sharedIsConnected = false
let isManualClose = false  // 模块级，非 useRef：避免实例卸载后 onClose 捕获 stale ref 导致僵尸重连

/**
 * WebSocket 连接管理 Hook。
 * 功能：自动连接、指数退避重连、心跳、事件分发。
 * 单例模式：多个 Hook 调用共享同一 WebSocket 连接，
 * 通过 connectionCount 引用计数管理生命周期。
 */
export function useWebSocket() {
  const { accessToken } = useAuthStore()
  const { setWsConnected, fetchUnreadCount, addNotification } = useNotificationStore()
  // 使用 useRef 引用模块级单例变量，确保多 Hook 实例共享
  const socketRef = useRef<Taro.SocketTask | null>(sharedSocket)
  const retryCountRef = useRef(0)
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [isConnected, setIsConnected] = useState(sharedIsConnected)
  const listenersRef = useRef<Set<Function>>(sharedListeners)

  const handleMessage = useCallback((data: string) => {
    try {
      const msg = JSON.parse(data)
      switch (msg.event) {
        case 'connected':
          setWsConnected(true)
          retryCountRef.current = 0
          break
        case 'notification':
          addNotification(msg.data as NotificationItem)
          break
        case 'analysis_progress':
          // 由 videoAnalysis store 处理
          Taro.eventCenter.trigger('analysis_progress', msg.data)
          break
        case 'analysis_complete':
          Taro.eventCenter.trigger('analysis_complete', msg.data)
          break
        case 'analysis_failed':
          Taro.eventCenter.trigger('analysis_failed', msg.data)
          break
        case 'score_update':
          Taro.eventCenter.trigger('score_update', msg.data)
          break
        case 'sync':
          fetchUnreadCount()
          break
        case 'payment_success':
          Taro.eventCenter.trigger('payment_success', msg.data)
          break
        case 'pong':
          // 心跳响应，token_expired=true 时需刷新
          if (msg.data?.token_expired) {
            useAuthStore.getState().refreshAccessToken()
          }
          break
      }
    } catch (e) {
      console.error('[WS] message parse error', e)
    }
  }, [setWsConnected, addNotification, fetchUnreadCount])

  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current)
    heartbeatTimerRef.current = setInterval(() => {
      socketRef.current?.send({
        data: JSON.stringify({ event: 'ping' }),
        fail: () => connect(),
      })
    }, HEARTBEAT_INTERVAL)
  }, [])

  const connect = useCallback(() => {
    isManualClose = false  // 模块级：重置手动关闭标志，允许连接/重连
    if (!accessToken) return

    // 单例：如果已有连接，不重复创建
    if (sharedSocket) {
      socketRef.current = sharedSocket
      setIsConnected(sharedIsConnected)
      return
    }

    const wsUrl = `${process.env.TARO_APP_WS_URL || 'wss://api.pingpongai.com/ws'}?token=${accessToken}`
    const task = Taro.connectSocket({ url: wsUrl })

    task.onOpen(() => {
      retryCountRef.current = 0
      sharedIsConnected = true
      setIsConnected(true)
      startHeartbeat()
    })

    task.onMessage((res) => {
      handleMessage(res.data)
      listenersRef.current.forEach((handler) => handler(res))
    })

    task.onClose(() => {
      setWsConnected(false)
      sharedIsConnected = false
      setIsConnected(false)
      sharedSocket = null
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current)
      }
      // 指数退避重连
      if (!isManualClose && retryCountRef.current < MAX_RETRIES) {
        const delay = BACKOFF[retryCountRef.current] || 16000
        retryCountRef.current++
        setTimeout(() => connect(), delay)
      }
    })

    task.onError(() => {
      // onClose 会跟随触发
      sharedIsConnected = false
      setIsConnected(false)
    })

    sharedSocket = task
    socketRef.current = task
  }, [accessToken, handleMessage, startHeartbeat, setWsConnected])

  const disconnect = useCallback(() => {
    // 引用计数：仅当所有调用方都断开时才真正关闭连接
    connectionCount = Math.max(0, connectionCount - 1)
    if (connectionCount > 0) return

    isManualClose = true
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current)
    }
    socketRef.current?.close({})
    socketRef.current = null
    sharedSocket = null
  }, [])

  const sendMessage = useCallback((data: string) => {
    socketRef.current?.send({ data })
  }, [])

  const onMessage = useCallback((handler: Function) => {
    listenersRef.current.add(handler)
    return () => { listenersRef.current.delete(handler) }
  }, [])

  useEffect(() => {
    // 引用计数 +1，确保多 Hook 实例共享连接
    connectionCount++
    if (accessToken) {
      connect()
    }
    return () => {
      disconnect()
    }
  }, [accessToken, connect, disconnect])

  return { connect, disconnect, sendMessage, isConnected, onMessage }
}
```

---

## 5. 通知中心铃铛组件

```tsx
// frontend/src/components/NotificationBell.tsx
import { FC, useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useNotificationStore } from '@/stores/notificationStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useTranslation } from 'react-i18next'
import './NotificationBell.scss'

interface NotificationBellProps {
  /** 点击跳转路径 */
  redirectTo?: string
}

/**
 * 通知铃铛组件——显示在首页顶部。
 * 功能：未读计数红点、点击跳转通知列表。
 */
const NotificationBell: FC<NotificationBellProps> = ({
  redirectTo = '/pages/notification/list/index',
}) => {
  const { t } = useTranslation()
  const { unreadCount, fetchUnreadCount } = useNotificationStore()

  useWebSocket() // 在铃铛组件中初始化 WebSocket

  useEffect(() => {
    fetchUnreadCount()
  }, [fetchUnreadCount])

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
```

```scss
// frontend/src/components/NotificationBell.scss
.notif-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px; /* P3-fix: icon dimension, not 8px grid spacing */
  height: 40px; /* P3-fix: icon dimension, not 8px grid spacing */

  &-icon {
    font-size: 18px;
  }

  &-badge {
    position: absolute;
    top: var(--spacing-xs); /* P3-fix: 2px→var(--spacing-xs) */
    right: var(--spacing-xs); /* P3-fix: 2px→var(--spacing-xs) */
    min-width: 16px;
    height: 16px;
    padding: 0 var(--spacing-xs);
    background: var(--color-primary); /* #E63946 */
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;

    &-text {
      font-size: 12px;
      color: var(--color-text-inverse);
      line-height: 1;
    }
  }
}
```

---

## 6. 通知列表页

```tsx
// frontend/src/pages/notification/list/index.tsx
import { useEffect, useCallback } from 'react'
import Taro, { usePullDownRefresh, useReachBottom } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Button, Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useNotificationStore } from '@/stores/notificationStore'
import './list.scss'

/**
 * 通知列表页。
 * 功能：分页加载、下拉刷新、上拉加载更多、标记已读、按类型展示。
 */
export default function NotificationList() {
  const { t, i18n } = useTranslation()
  const {
    notifications,
    isLoading,
    hasMore,
    unreadCount,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
    reset,
  } = useNotificationStore()

  useEffect(() => {
    fetchNotifications(true)
    return () => reset()
  }, [fetchNotifications, reset])

  // 下拉刷新
  usePullDownRefresh(() => {
    fetchNotifications(true).then(() => {
      Taro.stopPullDownRefresh()
    })
  })

  // 上拉加载更多
  useReachBottom(() => {
    fetchNotifications(false)
  })

  /** 处理通知点击 */
  const handleNotificationClick = useCallback(
    (item: typeof notifications[0]) => {
      if (!item.is_read) {
        markAsRead([item.id])
      }
      // 根据类型跳转
      if (item.extra_data?.action_url) {
        Taro.navigateTo({ url: item.extra_data.action_url })
      }
    },
    [markAsRead]
  )

  /** 格式化时间 */
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

  /** 获取通知图标 */
  const getNotifIcon = (type: string) => {
    const iconMap: Record<string, string> = {
      analysis_complete: '📊',
      payment_success: '💳',
      training_reminder: '🏓',
      score_update: '🏆',
      badge_unlocked: '🎖️',
    }
    return iconMap[type] || '📢'
  }

  return (
    <View className="notification-list">
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
      {notifications.length === 0 && !isLoading ? (
        <Empty description={t('notification.empty')} />
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
                  <Text className="notification-item-desc">
                    {item.content}
                  </Text>
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
          <Skeleton rows={2} animated />
        </View>
      )}
      {!hasMore && notifications.length > 0 && (
        <View className="notification-end">
          <Text className="notification-end-text">
            {t('common.noMore')}
          </Text>
        </View>
      )}
    </View>
  )
}
```

```scss
// frontend/src/pages/notification/list/list.scss
.notification-list {
  min-height: 100vh;
  background: var(--color-background);
}

.notification-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-card);

  &-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-secondary); /* #1D3557 */
  }
}

.notification-items {
  padding: 0 var(--spacing-md);
}

.notification-item {
  margin-top: var(--spacing-sm);
  border-radius: var(--radius-md);
  overflow: hidden;

  &.unread {
    background: color-mix(in srgb, var(--color-primary) 4%, transparent);
    border-left: 3px solid var(--color-primary); /* #E63946 */
  }

  &-inner {
    display: flex;
    align-items: flex-start;
    gap: var(--spacing-sm-md);
  }

  &-icon {
    position: relative;
    width: 40px; /* P3-fix: icon dimension, not 8px grid spacing */
    height: 40px; /* P3-fix: icon dimension, not 8px grid spacing */
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-card);
    border-radius: 50%;

    &-text {
      font-size: 18px;
    }
  }

  &-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }

  &-title {
    font-size: 15px;
    font-weight: 500;
    color: var(--color-secondary);
  }

  &-desc {
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.4;
  }

  &-time {
    font-size: 12px;
    color: var(--color-text-secondary);
  }
}

.unread-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  background: var(--color-primary); /* #E63946 */
  border-radius: 50%;
}

.notification-loading,
.notification-end {
  padding: var(--spacing-lg) 0;
  text-align: center;

  &-text {
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}
```

---

## 7. 路由配置

```typescript
// frontend/src/app.config.ts（新增 notification 页面）
export default {
  pages: [
    'pages/home/index',
    // ...
    'pages/notification/list/index',  // 新增：通知列表页
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 8. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "notification": {
    "title": "通知中心",
    "markAllRead": "全部已读",
    "empty": "暂无通知",
    "types": {
      "analysis_complete": "分析完成",
      "payment_success": "支付成功",
      "training_reminder": "训练提醒",
      "score_update": "比分更新",
      "badge_unlocked": "徽章解锁"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "notification": {
    "title": "Notifications",
    "markAllRead": "Mark All Read",
    "empty": "No notifications",
    "types": {
      "analysis_complete": "Analysis Complete",
      "payment_success": "Payment Success",
      "training_reminder": "Training Reminder",
      "score_update": "Score Update",
      "badge_unlocked": "Badge Unlocked"
    }
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
- [ ] 通知铃铛在首页正确显示
- [ ] 未读计数红点（>99 显示 99+）
- [ ] 通知列表页布局合理（图标+标题+内容+时间）
- [ ] 未读通知有红点标记和左侧红色边框
- [ ] 已读通知灰色样式区分
- [ ] 空状态正确显示 Empty 组件
- [ ] 下拉刷新动画正常
- [ ] 上拉加载更多提示正确

### 功能验证
- [ ] 通知列表分页加载（20条/页）
- [ ] 下拉刷新重置列表
- [ ] 点击未读通知自动标记已读
- [ ] 点击通知跳转到对应页面（extra_data.action_url）
- [ ] 全部已读按钮正确标记所有未读
- [ ] WebSocket 连接成功后铃铛实时更新未读数
- [ ] WebSocket 断连后指数退避重连（1s→2s→4s→8s→16s）
- [ ] 重连后触发 sync 事件拉取未读计数
- [ ] 收到 notification 事件实时添加到列表顶部

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** WebSocket 连接通过自定义 Hook `useWebSocket` 管理，**禁止** 在组件中直接 `connectSocket`
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量
- **禁止** 安装新的 npm 包
- WebSocket 重连 **必须** 使用指数退避策略，**禁止** 固定间隔或无限重连
- 心跳间隔 **必须** 为 30s，**禁止** 过短或过长
