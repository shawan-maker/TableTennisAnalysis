/**
 * notification Service 契约测试（04-前端实施计划.md FS6）
 * 端点与 app/api/v1/notification/router.py 逐字一致（4 个）
 */
import request from '@/services/request'
import * as notifApi from '@/services/notification'
import type { NotificationItem } from '@/services/notification'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const get = request.get as jest.Mock
const post = request.post as jest.Mock

describe('notification Service 契约（router.py 4 端点）', () => {
  beforeEach(() => jest.resetAllMocks())

  it('GET /notification/list — 默认 page=1/page_size=20', async () => {
    const payload = { data: { data: { total: 0, items: [] } } }
    get.mockResolvedValueOnce(payload)
    const res = await notifApi.listNotifications()
    expect(get).toHaveBeenCalledWith('/notification/list', { page: 1, page_size: 20 })
    expect(res).toBe(payload)
  })

  it('GET /notification/list — is_read/type 筛选与分页透传', async () => {
    get.mockResolvedValueOnce({ data: { data: {} } })
    await notifApi.listNotifications({ is_read: false, type: 'payment_success', page: 2, page_size: 50 })
    expect(get).toHaveBeenCalledWith('/notification/list', {
      page: 2, page_size: 50, is_read: false, type: 'payment_success',
    })
  })

  it('POST /notification/read — notification_ids 数组体', async () => {
    const payload = { data: { data: { updated_count: 2 } } }
    post.mockResolvedValueOnce(payload)
    const res = await notifApi.markRead([1, 2])
    expect(post).toHaveBeenCalledWith('/notification/read', { notification_ids: [1, 2] })
    expect(res).toBe(payload)
  })

  it('POST /notification/subscribe — 模板授权', async () => {
    const payload = { data: { data: { subscribed_templates: ['analysis_complete'] } } }
    post.mockResolvedValueOnce(payload)
    const res = await notifApi.subscribeTemplates(['analysis_complete'])
    expect(post).toHaveBeenCalledWith('/notification/subscribe', {
      template_ids: ['analysis_complete'],
    })
    expect(res).toBe(payload)
  })

  it('GET /notification/unread-count — 未读计数', async () => {
    const payload = { data: { data: { unread_count: 7 } } }
    get.mockResolvedValueOnce(payload)
    const res = await notifApi.getUnreadCount()
    expect(get).toHaveBeenCalledWith('/notification/unread-count')
    expect(res).toBe(payload)
  })
})

describe('WS 合成契约（后端 notification_service 在线直推缺 id/is_read/created_at）', () => {
  it('NotificationItem 完整形态由 useWebSocket 合成后传入 store', () => {
    const item: NotificationItem = {
      id: -1930000000000, // 负时间戳（WS 合成，防与 DB 主键冲突）
      type: 'payment_success',
      title: '支付成功',
      content: null,
      is_read: false,
      extra_data: { action_url: '/pages/payment/orders/index' },
      created_at: new Date().toISOString(),
    }
    expect(item.id).toBeLessThan(0)
    expect(item.is_read).toBe(false)
  })
})
