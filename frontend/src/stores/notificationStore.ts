/**
 * 通知状态管理（12-notification/frontend.md §3）
 * 分页列表 + 未读计数 + WS 实时插入。
 *
 * FS6-P3 契约同步（后端 notification_service）：
 * - addNotification 消费 WS notification 事件合成的 item（后端在线用户直推
 *   {type,title,content,extra_data}，无 id/is_read/created_at，由 useWebSocket
 *   合成后插入，id 用负时间戳避免与 DB 主键冲突）
 * - setUnreadCount 为新增 action：重连补偿 sync 事件 data 直接携带
 *   unread_count（on_ws_reconnect），直接消费避免二次 HTTP
 */
import { create } from 'zustand'
import * as notifApi from '@/services/notification'
import type { NotificationItem } from '@/services/notification'

interface NotificationState {
  unreadCount: number
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
  setUnreadCount: (count: number) => void
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

  setUnreadCount: (count) => set({ unreadCount: Math.max(0, count) }),

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
