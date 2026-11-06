/**
 * membershipStore 状态机测试（04-前端实施计划.md FS6）
 * 覆盖：三接口独立 loading、refreshAll 并行、错误静默（Skeleton 兜底）
 */
import * as membershipApi from '@/services/membership'
import { useMembershipStore } from '@/stores/membershipStore'

jest.mock('@/services/membership', () => ({
  __esModule: true,
  getTiers: jest.fn(),
  getCurrentMembership: jest.fn(),
  getQuota: jest.fn(),
}))

const getTiers = membershipApi.getTiers as jest.Mock
const getCurrentMembership = membershipApi.getCurrentMembership as jest.Mock
const getQuota = membershipApi.getQuota as jest.Mock

describe('membershipStore', () => {
  beforeEach(() => {
    jest.resetAllMocks()
    useMembershipStore.setState({
      tiers: null,
      current: null,
      quota: null,
      isLoadingTiers: false,
      isLoadingCurrent: false,
      isLoadingQuota: false,
    })
  })

  it('fetchTiers 写入等级列表（后端 MembershipTierConfig 权威源）', async () => {
    const payload = { data: { data: { tiers: [
      { tier: 'free', name: '免费版', price_monthly_cents: 0, price_quarterly_cents: 0, price_yearly_cents: 0, benefits: [], quota_config: {} },
      { tier: 'member', name: '会员版', price_monthly_cents: 1900, price_quarterly_cents: 4900, price_yearly_cents: 16800, benefits: ['无限分析'], quota_config: {} },
    ] } } }
    getTiers.mockResolvedValueOnce(payload)
    await useMembershipStore.getState().fetchTiers()
    const s = useMembershipStore.getState()
    expect(s.tiers).toBe(payload.data.data)
    expect(s.isLoadingTiers).toBe(false)
  })

  it('fetchCurrent 写入当前会员状态（含 days_remaining）', async () => {
    const payload = { data: { data: { tier: 'member', status: 'active', start_at: 's', expire_at: 'e', days_remaining: 30, auto_renew: true } } }
    getCurrentMembership.mockResolvedValueOnce(payload)
    await useMembershipStore.getState().fetchCurrent()
    expect(useMembershipStore.getState().current?.days_remaining).toBe(30)
  })

  it('fetchQuota 写入今日额度（含 bonus_remaining）', async () => {
    const payload = { data: { data: { tier: 'free', daily_limit: 3, used_today: 1, remaining: 2, reset_at: 'r', bonus_remaining: 0 } } }
    getQuota.mockResolvedValueOnce(payload)
    await useMembershipStore.getState().fetchQuota()
    expect(useMembershipStore.getState().quota?.remaining).toBe(2)
  })

  it('refreshAll 并行刷新三接口（支付成功权益即时刷新）', async () => {
    getTiers.mockResolvedValueOnce({ data: { data: { tiers: [] } } })
    getCurrentMembership.mockResolvedValueOnce({ data: { data: { tier: 'free' } } })
    getQuota.mockResolvedValueOnce({ data: { data: { remaining: 3 } } })
    await useMembershipStore.getState().refreshAll()
    expect(getTiers).toHaveBeenCalledTimes(1)
    expect(getCurrentMembership).toHaveBeenCalledTimes(1)
    expect(getQuota).toHaveBeenCalledTimes(1)
  })

  it('接口失败静默不抛错（页面 Skeleton/空态兜底），loading 复位', async () => {
    getTiers.mockRejectedValueOnce(new Error('network'))
    await expect(useMembershipStore.getState().fetchTiers()).resolves.toBeUndefined()
    const s = useMembershipStore.getState()
    expect(s.tiers).toBeNull()
    expect(s.isLoadingTiers).toBe(false)
  })
})
