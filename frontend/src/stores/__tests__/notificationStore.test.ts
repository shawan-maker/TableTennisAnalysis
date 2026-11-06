/**
 * notificationStore 状态机测试（04-前端实施计划.md FS6）
 * 覆盖：分页 reset/append/守卫、markAsRead 本地+计数、markAllAsRead、
 * addNotification 头插计数、setUnreadCount（sync 事件）、fetchUnreadCount
 */
import * as notifApi from '@/services/notification'
import { useNotificationStore } from '@/stores/notificationStore'

jest.mock('@/services/notification', () => ({
  __esModule: true,
  getUnreadCount: jest.fn(),
  listNotifications: jest.fn(),
  markRead: jest.fn(),
  subscribeTemplates: jest.fn(),
}))

const listNotifications = notifApi.listNotifications as jest.Mock
const markRead = notifApi.markRead as jest.Mock
const getUnreadCount = notifApi.getUnreadCount as jest.Mock

const PAGE = (page: number, ids: number[], unreadFlags: boolean[] = []) => ({
  data: {
    data: {
      total: 100,
      page,
      page_size: 20,
      items: ids.map((id, i) => ({
        id,
        type: 'system',
        title: `通知${id}`,
        content: null,
        is_read: unreadFlags[i] ?? false,
        extra_data: null,
        created_at: `2026-11-06T10:00:${String(id).padStart(2, '0')}Z`,
      })),
    },
  },
})

describe('notificationStore', () => {
  beforeEach(() => {
    jest.resetAllMocks()
    useNotificationStore.setState({
      unreadCount: 0,
      notifications: [],
      hasMore: true,
      currentPage: 1,
      isLoading: false,
      wsConnected: false,
    })
  })

  describe('fetchNotifications 分页', () => {
    it('reset=true 拉第 1 页并整表替换', async () => {
      listNotifications.mockResolvedValueOnce(PAGE(1, [1, 2]))
      await useNotificationStore.getState().fetchNotifications(true)
      const s = useNotificationStore.getState()
      expect(listNotifications).toHaveBeenCalledWith({ page: 1, page_size: 20 })
      expect(s.notifications.map((n) => n.id)).toEqual([1, 2])
      expect(s.currentPage).toBe(1)
      expect(s.hasMore).toBe(false) // < 20 条
    })

    it('reset=false 追加下一页且 >=20 条置 hasMore', async () => {
      listNotifications.mockResolvedValueOnce(PAGE(1, Array.from({ length: 20 }, (_, i) => i + 1)))
      await useNotificationStore.getState().fetchNotifications(true)
      listNotifications.mockResolvedValueOnce(PAGE(2, [21, 22]))
      await useNotificationStore.getState().fetchNotifications(false)
      const s = useNotificationStore.getState()
      expect(listNotifications).toHaveBeenLastCalledWith({ page: 2, page_size: 20 })
      expect(s.notifications).toHaveLength(22)
      expect(s.currentPage).toBe(2)
    })

    it('筛选透传（unread Tab：is_read=false）', async () => {
      listNotifications.mockResolvedValueOnce(PAGE(1, [1]))
      await useNotificationStore.getState().fetchNotifications(true, { is_read: false })
      expect(listNotifications).toHaveBeenCalledWith({ page: 1, page_size: 20, is_read: false })
    })

    it('hasMore=false 时非 reset 调用直接返回（不再翻页）', async () => {
      useNotificationStore.setState({ hasMore: false, currentPage: 3 })
      await useNotificationStore.getState().fetchNotifications(false)
      expect(listNotifications).not.toHaveBeenCalled()
    })

    it('isLoading=true 时并发调用被守卫（防重复请求）', async () => {
      useNotificationStore.setState({ isLoading: true })
      await useNotificationStore.getState().fetchNotifications(true)
      expect(listNotifications).not.toHaveBeenCalled()
      expect(useNotificationStore.getState().isLoading).toBe(true)
    })
  })

  describe('markAsRead / markAllAsRead', () => {
    it('markAsRead 按 updated_count 更新本地 is_read 与未读数', async () => {
      useNotificationStore.setState({
        notifications: [
          { id: 1, type: 'a', title: 'A', content: null, is_read: false, extra_data: null, created_at: 't' },
          { id: 2, type: 'b', title: 'B', content: null, is_read: false, extra_data: null, created_at: 't' },
        ],
        unreadCount: 2,
      })
      markRead.mockResolvedValueOnce({ data: { data: { updated_count: 2 } } })
      await useNotificationStore.getState().markAsRead([1, 2])
      const s = useNotificationStore.getState()
      expect(markRead).toHaveBeenCalledWith([1, 2])
      expect(s.notifications.every((n) => n.is_read)).toBe(true)
      expect(s.unreadCount).toBe(0)
    })

    it('markAllAsRead 只提交列表中未读的 id', async () => {
      useNotificationStore.setState({
        notifications: [
          { id: 1, type: 'a', title: 'A', content: null, is_read: true, extra_data: null, created_at: 't' },
          { id: 2, type: 'b', title: 'B', content: null, is_read: false, extra_data: null, created_at: 't' },
          { id: 3, type: 'c', title: 'C', content: null, is_read: false, extra_data: null, created_at: 't' },
        ],
        unreadCount: 2,
      })
      markRead.mockResolvedValueOnce({ data: { data: { updated_count: 2 } } })
      await useNotificationStore.getState().markAllAsRead()
      expect(markRead).toHaveBeenCalledWith([2, 3])
    })

    it('markAllAsRead 无未读时不发请求', async () => {
      useNotificationStore.setState({
        notifications: [
          { id: 1, type: 'a', title: 'A', content: null, is_read: true, extra_data: null, created_at: 't' },
        ],
      })
      await useNotificationStore.getState().markAllAsRead()
      expect(markRead).not.toHaveBeenCalled()
    })
  })

  describe('WS 实时 / 计数', () => {
    it('addNotification 头部插入 + 未读计数 +1（WS notification 事件消费）', () => {
      useNotificationStore.setState({
        notifications: [
          { id: 5, type: 'a', title: 'A', content: null, is_read: true, extra_data: null, created_at: 't' },
        ],
        unreadCount: 1,
      })
      useNotificationStore.getState().addNotification({
        id: -1, type: 'payment_success', title: '支付成功',
        content: null, is_read: false, extra_data: null, created_at: 'now',
      })
      const s = useNotificationStore.getState()
      expect(s.notifications[0].id).toBe(-1)
      expect(s.notifications).toHaveLength(2)
      expect(s.unreadCount).toBe(2)
    })

    it('setUnreadCount（sync 事件 data.unread_count 直接消费）', () => {
      useNotificationStore.getState().setUnreadCount(99)
      expect(useNotificationStore.getState().unreadCount).toBe(99)
    })

    it('fetchUnreadCount 写入接口返回值（静默失败不打扰）', async () => {
      getUnreadCount.mockResolvedValueOnce({ data: { data: { unread_count: 7 } } })
      await useNotificationStore.getState().fetchUnreadCount()
      expect(useNotificationStore.getState().unreadCount).toBe(7)
    })

    it('fetchUnreadCount 接口异常静默（unreadCount 保持）', async () => {
      getUnreadCount.mockRejectedValueOnce(new Error('network'))
      await useNotificationStore.getState().fetchUnreadCount()
      expect(useNotificationStore.getState().unreadCount).toBe(0)
    })
  })

  it('reset 只重置分页状态（unreadCount 保留给铃铛）', () => {
    useNotificationStore.setState({
      notifications: [{ id: 1, type: 'a', title: 'A', content: null, is_read: true, extra_data: null, created_at: 't' }],
      hasMore: false,
      currentPage: 3,
      unreadCount: 4,
    })
    useNotificationStore.getState().reset()
    const s = useNotificationStore.getState()
    expect(s.notifications).toEqual([])
    expect(s.currentPage).toBe(1)
    expect(s.hasMore).toBe(true)
    expect(s.unreadCount).toBe(4)
  })
})
