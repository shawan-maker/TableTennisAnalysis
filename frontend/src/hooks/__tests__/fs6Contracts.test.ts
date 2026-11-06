/**
 * FS6 hook/常量契约测试（04-前端实施计划.md FS6）
 * 覆盖：useMembershipGate 判定矩阵（computeMembershipAccess）、
 * useWebSocket 内置事件五件（handleBuiltinEvent：connected/notification/sync/
 * export_completed/membership_downgrade）、
 * membership 常量（TIER_ORDER/EXPIRED_ACCESS_MAP/MEMBERSHIP_STATUS_MAP labelKey 双语存在性）
 */
import { computeMembershipAccess } from '@/hooks/useMembershipGate'
import { handleBuiltinEvent, buildWsUrl } from '@/hooks/useWebSocket'
import { useNotificationStore } from '@/stores/notificationStore'
import * as notifApi from '@/services/notification'
import * as memberApi from '@/services/membership'
import {
  TIER_ORDER, EXPIRED_ACCESS_MAP, MEMBERSHIP_STATUS_MAP, USER_TAB_INDEX,
} from '@/constants/membership'
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

jest.mock('@/services/notification', () => ({
  __esModule: true,
  getUnreadCount: jest.fn(),
  listNotifications: jest.fn(),
  markRead: jest.fn(),
  subscribeTemplates: jest.fn(),
}))

jest.mock('@/services/membership', () => ({
  __esModule: true,
  getTiers: jest.fn(),
  getCurrentMembership: jest.fn(),
  getQuota: jest.fn(),
}))

const getUnreadCount = notifApi.getUnreadCount as jest.Mock
const getTiers = memberApi.getTiers as jest.Mock
const getCurrentMembership = memberApi.getCurrentMembership as jest.Mock
const getQuota = memberApi.getQuota as jest.Mock

describe('computeMembershipAccess 判定矩阵（10-membership §8）', () => {
  it('free + hidden 功能（3D 教学/进度分析）→ 不可访问', () => {
    expect(computeMembershipAccess('free', 'none', 'teaching_3d')).toBe(false)
    expect(computeMembershipAccess('free', 'none', 'progress_analysis')).toBe(false)
  })

  it('free + readonly/basic/30days 功能 → 可访问', () => {
    expect(computeMembershipAccess('free', 'none', 'analysis_reports')).toBe(true)
    expect(computeMembershipAccess('free', 'none', 'training_plan')).toBe(true)
    expect(computeMembershipAccess('free', 'none', 'annotated_video')).toBe(true)
    expect(computeMembershipAccess('free', 'none', 'dashboard')).toBe(true)
  })

  it('expired/closed + hidden 功能 → 不可访问', () => {
    expect(computeMembershipAccess('pro', 'expired', 'teaching_3d')).toBe(false)
    expect(computeMembershipAccess('pro', 'closed', 'progress_analysis')).toBe(false)
  })

  it('active 会员全功能放行（grace_period 不降级）', () => {
    expect(computeMembershipAccess('member', 'active', 'teaching_3d')).toBe(true)
    expect(computeMembershipAccess('coach', 'grace_period', 'progress_analysis')).toBe(true)
  })
})

describe('handleBuiltinEvent 内置通知域事件（12-notification §4，连接级单次消化）', () => {
  beforeEach(() => {
    jest.resetAllMocks()
    getUnreadCount.mockResolvedValue({ data: { data: { unread_count: 0 } } })
    useNotificationStore.setState({
      unreadCount: 0,
      notifications: [],
      hasMore: true,
      currentPage: 1,
      isLoading: false,
      wsConnected: false,
    })
  })

  it('connected → setWsConnected(true) 且不再分发', () => {
    const consumed = handleBuiltinEvent({ event: 'connected', data: { user_id: 1 } })
    expect(consumed).toBe(true)
    expect(useNotificationStore.getState().wsConnected).toBe(true)
  })

  it('notification → 合成完整 item 头插 + 未读 +1（后端在线直推无 id/is_read/created_at）', () => {
    const consumed = handleBuiltinEvent({
      event: 'notification',
      data: { type: 'payment_success', title: '支付成功', content: '订单已支付', extra_data: { order_id: 42 } },
    })
    expect(consumed).toBe(true)
    const s = useNotificationStore.getState()
    expect(s.notifications).toHaveLength(1)
    const item = s.notifications[0]
    expect(item.id).toBeLessThan(0) // 负时间戳防 DB 主键冲突
    expect(item.is_read).toBe(false)
    expect(item.type).toBe('payment_success')
    expect(item.title).toBe('支付成功')
    expect(item.created_at).toBeTruthy()
    expect(s.unreadCount).toBe(1)
  })

  it('sync 且 data.unread_count 存在 → 直接 setUnreadCount（on_ws_reconnect 重连补偿）', () => {
    const consumed = handleBuiltinEvent({
      event: 'sync',
      data: { type: 'notification', unread_count: 9, message: '您有 9 条未读通知' },
    })
    expect(consumed).toBe(true)
    expect(useNotificationStore.getState().unreadCount).toBe(9)
    expect(getUnreadCount).not.toHaveBeenCalled()
  })

  it('sync 缺 unread_count → 回退 fetchUnreadCount（HTTP 兜底）', () => {
    const consumed = handleBuiltinEvent({ event: 'sync', data: {} })
    expect(consumed).toBe(true)
    expect(getUnreadCount).toHaveBeenCalledTimes(1)
  })

  it('export_completed → fetchUnreadCount 刷新角标（实施计划角标三事件之一）', () => {
    const consumed = handleBuiltinEvent({ event: 'export_completed', data: { task_id: 'T1' } })
    expect(consumed).toBe(true)
    expect(getUnreadCount).toHaveBeenCalledTimes(1)
  })

  it('membership_downgrade → membershipStore.refreshAll 三接口静默刷新（10-membership §9）', async () => {
    getTiers.mockResolvedValue({ data: { data: { tiers: [] } } })
    getCurrentMembership.mockResolvedValue({ data: { data: {} } })
    getQuota.mockResolvedValue({ data: { data: {} } })
    const consumed = handleBuiltinEvent({ event: 'membership_downgrade', data: {} })
    expect(consumed).toBe(true)
    await new Promise((r) => setTimeout(r, 0))
    expect(getTiers).toHaveBeenCalledTimes(1)
    expect(getCurrentMembership).toHaveBeenCalledTimes(1)
    expect(getQuota).toHaveBeenCalledTimes(1)
  })

  it('badge_unlocked / payment_success → 不消化（分发给领域 Hook）', () => {
    expect(handleBuiltinEvent({ event: 'badge_unlocked', data: [{ badge_id: 1 }] })).toBe(false)
    expect(handleBuiltinEvent({ event: 'payment_success', data: { order_id: 42 } })).toBe(false)
  })
})

describe('membership 常量（10-membership §7）', () => {
  it('TIER_ORDER 四级顺序', () => {
    expect(TIER_ORDER).toEqual(['free', 'member', 'pro', 'coach'])
  })

  it('EXPIRED_ACCESS_MAP 六功能访问级别', () => {
    expect(EXPIRED_ACCESS_MAP.analysis_reports).toBe('readonly')
    expect(EXPIRED_ACCESS_MAP.annotated_video).toBe('30days')
    expect(EXPIRED_ACCESS_MAP.training_plan).toBe('readonly')
    expect(EXPIRED_ACCESS_MAP.teaching_3d).toBe('hidden')
    expect(EXPIRED_ACCESS_MAP.progress_analysis).toBe('hidden')
    expect(EXPIRED_ACCESS_MAP.dashboard).toBe('basic')
  })

  it('MEMBERSHIP_STATUS_MAP 六状态 labelKey 双语全覆盖', () => {
    const statuses = ['active', 'expiring_soon', 'expired', 'grace_period', 'closed', 'none']
    statuses.forEach((status) => {
      const config = MEMBERSHIP_STATUS_MAP[status]
      expect(config).toBeDefined()
      expect(zhCN.membership).toHaveProperty(config.labelKey.split('.')[1])
      expect(enUS.membership).toHaveProperty(config.labelKey.split('.')[1])
    })
  })

  it('USER_TAB_INDEX=4（「我的」Tab 角标挂载点）', () => {
    expect(USER_TAB_INDEX).toBe(4)
  })
})

describe('buildWsUrl（API §14.1）', () => {
  it('默认生产 wss 地址（Token 走子协议不入 URL）', () => {
    expect(buildWsUrl()).toBe('wss://api.pingpongai.com/ws')
  })
})
