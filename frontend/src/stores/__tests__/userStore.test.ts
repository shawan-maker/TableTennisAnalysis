/**
 * userStore 单元测试（02-user/frontend.md §3 + R3-P2-6 恢复面保护）
 * - fetchDeletionStatus 三分支：pending_deletion → cooling 映射 / active → null / 失败静默
 * - 注销生命周期：requestDeletion 72h 前端推算 → cancelDeletion 清态（撤销权可达性）
 * - 修复守卫背景：R3-P2-6 恢复 fetchDeletionStatus 前该 store 零 Jest 覆盖
 *   （Round 4 复审发现 R4-2，存量缺口），本文件以最小集保护 R3-P2-6 契约面
 */
import * as userApi from '@/services/user'
import { useUserStore } from '@/stores/userStore'

jest.mock('@/services/user', () => ({
  __esModule: true,
  getProfile: jest.fn(),
  updateProfile: jest.fn(),
  updateRating: jest.fn(),
  getRatingHistory: jest.fn(),
  getBigData: jest.fn(),
  deleteAccount: jest.fn(),
  cancelDeletion: jest.fn(),
  getDeletionStatus: jest.fn(),
  exportData: jest.fn(),
  getExportStatus: jest.fn(),
}))

const api = userApi as jest.Mocked<typeof userApi>
const store = useUserStore

const resetStore = () =>
  store.setState({
    profile: null,
    bigData: null,
    ratingHistory: [],
    ratingHistoryTotal: 0,
    isLoading: false,
    deletionState: null,
    deletionLoading: false,
    exportTask: null,
    exportLoading: false,
  })

describe('userStore 注销生命周期（X-23 + R3-P2-6）', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchDeletionStatus：pending_deletion → deletionState cooling 映射（契约键 requested_at/expires_at）', async () => {
    api.getDeletionStatus.mockResolvedValue({
      data: {
        data: {
          status: 'pending_deletion',
          requested_at: '2026-11-17T10:00:00Z',
          expires_at: '2026-11-20T10:00:00Z',
        },
      },
    } as any)

    await store.getState().fetchDeletionStatus()

    const s = store.getState().deletionState
    expect(s).not.toBeNull()
    expect(s?.status).toBe('cooling')
    expect(s?.scheduled_at).toBe('2026-11-17T10:00:00Z')
    expect(s?.cooling_ends_at).toBe('2026-11-20T10:00:00Z')
  })

  it('fetchDeletionStatus：active → deletionState null（无横幅即正常态）', async () => {
    store.setState({ deletionState: { status: 'cooling', scheduled_at: 'x', cooling_ends_at: 'y' } })
    api.getDeletionStatus.mockResolvedValue({
      data: { data: { status: 'active', requested_at: null, expires_at: null } },
    } as any)

    await store.getState().fetchDeletionStatus()

    expect(store.getState().deletionState).toBeNull()
  })

  it('fetchDeletionStatus：失败静默不抛错（best-effort，横幅缺省）', async () => {
    api.getDeletionStatus.mockRejectedValue(new Error('network'))
    await expect(store.getState().fetchDeletionStatus()).resolves.toBeUndefined()
    expect(store.getState().deletionState).toBeNull()
  })

  it('requestDeletion：成功 → cooling + cooling_ends_at ≈ 72h 后（POST 即刻态）', async () => {
    api.deleteAccount.mockResolvedValue({ data: { data: null } } as any)

    await store.getState().requestDeletion('不想用了')

    const s = store.getState().deletionState
    expect(s?.status).toBe('cooling')
    expect(s?.scheduled_at).not.toBeNull()
    const ends = new Date(s?.cooling_ends_at ?? '').getTime()
    const now = Date.now()
    // [now+71.5h, now+72.5h] 容差窗（执行耗时）
    expect(ends).toBeGreaterThan(now + 71.5 * 3600 * 1000)
    expect(ends).toBeLessThan(now + 72.5 * 3600 * 1000)
    expect(store.getState().deletionLoading).toBe(false)
  })

  it('cancelDeletion：成功 → deletionState 清空（撤销权闭环）', async () => {
    store.setState({ deletionState: { status: 'cooling', scheduled_at: 'x', cooling_ends_at: 'y' } })
    api.cancelDeletion.mockResolvedValue({ data: { data: null } } as any)

    await store.getState().cancelDeletion()

    expect(store.getState().deletionState).toBeNull()
    expect(store.getState().deletionLoading).toBe(false)
  })

  it('cancelDeletion：失败 → 抛错且状态保持（撤销失败不清冷静期）', async () => {
    const before = { status: 'cooling', scheduled_at: 'x', cooling_ends_at: 'y' } as const
    store.setState({ deletionState: { ...before } })
    api.cancelDeletion.mockRejectedValue(new Error('server error'))

    await expect(store.getState().cancelDeletion()).rejects.toThrow('server error')

    expect(store.getState().deletionState).toEqual({ ...before })
    expect(store.getState().deletionLoading).toBe(false)
  })
})
