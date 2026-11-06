/**
 * gamification Service 契约测试（04-前端实施计划.md FS5）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/gamification/router.py
 * 逐字一致（4 端点）
 */
import request from '@/services/request'
import * as gamificationApi from '@/services/gamification'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const get = request.get as jest.Mock
const post = request.post as jest.Mock

describe('services/gamification 契约（4 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getPoints → GET /gamification/points（无参数）', async () => {
    await gamificationApi.getPoints()
    expect(get).toHaveBeenCalledWith('/gamification/points')
  })

  it('getCheckinCalendar() → GET /gamification/checkin-calendar（空参数当月）', async () => {
    await gamificationApi.getCheckinCalendar()
    expect(get).toHaveBeenCalledWith('/gamification/checkin-calendar', {})
  })

  it('getCheckinCalendar(2026, 11) → 年月透传', async () => {
    await gamificationApi.getCheckinCalendar(2026, 11)
    expect(get).toHaveBeenCalledWith('/gamification/checkin-calendar', {
      year: 2026,
      month: 11,
    })
  })

  it('checkin → POST /gamification/checkin（无 body）', async () => {
    await gamificationApi.checkin()
    expect(post).toHaveBeenCalledWith('/gamification/checkin')
  })

  it('getBadges → GET /gamification/badges（无参数）', async () => {
    await gamificationApi.getBadges()
    expect(get).toHaveBeenCalledWith('/gamification/badges')
  })

  it('响应类型与后端字段对齐（bonus 可为 null，R6-Gami-2）', () => {
    // 编译期契约：bonus 无奖励时为 null 而非 0
    const result: gamificationApi.CheckInResult = {
      points_earned: 2,
      current_streak: 1,
      bonus: null,
    }
    expect(result.bonus).toBeNull()
  })
})
