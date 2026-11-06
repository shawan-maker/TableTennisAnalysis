/**
 * membership Service 契约测试（04-前端实施计划.md FS6）
 * 端点与 app/api/v1/membership/router.py 逐字一致（3 个 GET）；
 * FS6-P3 编译期契约：TierBrief 用 price_*_cents + quota_config、QuotaResponse 含 bonus_remaining
 */
import request from '@/services/request'
import * as membershipApi from '@/services/membership'
import type { TierInfo, CurrentMembershipData, QuotaData } from '@/services/membership'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const get = request.get as jest.Mock

describe('membership Service 契约（router.py 3 端点）', () => {
  beforeEach(() => jest.resetAllMocks())

  it('GET /membership/tiers — getTiers', async () => {
    const payload = { data: { data: { tiers: [] } } }
    get.mockResolvedValueOnce(payload)
    const res = await membershipApi.getTiers()
    expect(get).toHaveBeenCalledWith('/membership/tiers')
    expect(res).toBe(payload)
  })

  it('GET /membership/current — getCurrentMembership', async () => {
    const payload = { data: { data: { tier: 'member' } } }
    get.mockResolvedValueOnce(payload)
    const res = await membershipApi.getCurrentMembership()
    expect(get).toHaveBeenCalledWith('/membership/current')
    expect(res).toBe(payload)
  })

  it('GET /membership/quota — getQuota', async () => {
    const payload = { data: { data: { remaining: 2 } } }
    get.mockResolvedValueOnce(payload)
    const res = await membershipApi.getQuota()
    expect(get).toHaveBeenCalledWith('/membership/quota')
    expect(res).toBe(payload)
  })
})

describe('FS6-P3 编译期契约（后端 schemas/membership.py）', () => {
  it('TierInfo.price_*_cents 三档定价 + quota_config dict（设计样例缺 _cents/quota 嵌套）', () => {
    const tier: TierInfo = {
      tier: 'member',
      name: '会员版',
      price_monthly_cents: 1900,
      price_quarterly_cents: 4900,
      price_yearly_cents: 16800,
      benefits: ['无限分析'],
      quota_config: { daily_analysis_limit: 10 },
    }
    expect(tier.price_monthly_cents).toBe(1900)
    expect(tier.quota_config).toEqual({ daily_analysis_limit: 10 })
  })

  it('CurrentMembershipResponse 状态机字段', () => {
    const cur: CurrentMembershipData = {
      tier: 'free', status: 'none', start_at: null, expire_at: null,
      days_remaining: 0, auto_renew: false,
    }
    expect(cur.status).toBe('none')
  })

  it('QuotaResponse 含 bonus_remaining（R15-VA-N1 付费分析包剩余额度）', () => {
    const quota: QuotaData = {
      tier: 'free', daily_limit: 3, used_today: 1, remaining: 2,
      reset_at: '2026-11-06T16:00:00Z', bonus_remaining: 0,
    }
    expect(quota).toHaveProperty('bonus_remaining')
  })
})
