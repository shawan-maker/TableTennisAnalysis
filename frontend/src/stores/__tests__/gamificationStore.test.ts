/**
 * gamificationStore 状态机测试（04-前端实施计划.md FS5）
 * 覆盖：积分/日历/徽章加载、doCheckin 成功联动刷新、失败向上抛出
 */
import * as gamificationApi from '@/services/gamification'
import { useGamificationStore } from '@/stores/gamificationStore'

jest.mock('@/services/gamification', () => ({
  __esModule: true,
  getPoints: jest.fn(),
  getCheckinCalendar: jest.fn(),
  checkin: jest.fn(),
  getBadges: jest.fn(),
}))

const getPoints = gamificationApi.getPoints as jest.Mock
const getCheckinCalendar = gamificationApi.getCheckinCalendar as jest.Mock
const checkin = gamificationApi.checkin as jest.Mock
const getBadges = gamificationApi.getBadges as jest.Mock

const POINTS = { total_points: 100, monthly_points: 20, current_streak: 4, streak_icon: '🔥' }
const CALENDAR = {
  year: 2026,
  month: 11,
  days: [
    { date: '2026-11-01', checked_in: true, type: 'manual' },
    { date: '2026-11-02', checked_in: false, type: null },
  ],
  monthly_checkin_count: 1,
  streak_days: 4,
}
const BADGES = {
  earned: [{ badge_id: 'first_analysis', name: '首次分析', icon: '🏆', earned_at: '2026-11-01' }],
  locked: [{ badge_id: 'streak_7', name: '7天连续', icon: '🔥', progress: 4, target: 7 }],
}

describe('gamificationStore', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    useGamificationStore.setState({
      points: null,
      calendar: null,
      badges: null,
      isLoadingPoints: false,
      isLoadingCalendar: false,
      isLoadingBadges: false,
      isCheckingIn: false,
    })
  })

  it('fetchPoints 成功 → points 落库', async () => {
    getPoints.mockResolvedValue({ data: { data: POINTS } })
    await useGamificationStore.getState().fetchPoints()
    expect(getPoints).toHaveBeenCalledWith()
    expect(useGamificationStore.getState().points).toEqual(POINTS)
    expect(useGamificationStore.getState().isLoadingPoints).toBe(false)
  })

  it('fetchCalendar(2026, 11) → 年月透传 + calendar 落库', async () => {
    getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } })
    await useGamificationStore.getState().fetchCalendar(2026, 11)
    expect(getCheckinCalendar).toHaveBeenCalledWith(2026, 11)
    expect(useGamificationStore.getState().calendar).toEqual(CALENDAR)
  })

  it('fetchBadges 成功 → earned/locked 两组落库', async () => {
    getBadges.mockResolvedValue({ data: { data: BADGES } })
    await useGamificationStore.getState().fetchBadges()
    const s = useGamificationStore.getState()
    expect(s.badges?.earned).toHaveLength(1)
    expect(s.badges?.locked).toHaveLength(1)
    expect(s.badges?.locked[0].progress).toBe(4)
  })

  describe('doCheckin', () => {
    it('成功 → 返回结果 + 联动刷新积分与日历', async () => {
      checkin.mockResolvedValue({
        data: { data: { points_earned: 2, current_streak: 5, bonus: null } },
      })
      getPoints.mockResolvedValue({ data: { data: POINTS } })
      getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } })
      const result = await useGamificationStore.getState().doCheckin()
      expect(checkin).toHaveBeenCalledWith()
      expect(result).toEqual({ points_earned: 2, current_streak: 5, bonus: null })
      // 联动刷新：打卡后积分与日历被重新拉取
      expect(getPoints).toHaveBeenCalledTimes(1)
      expect(getCheckinCalendar).toHaveBeenCalledTimes(1)
      expect(useGamificationStore.getState().isCheckingIn).toBe(false)
    })

    it('成功（bonus 有值）→ 保留 streak bonus 数据', async () => {
      checkin.mockResolvedValue({
        data: { data: { points_earned: 2, current_streak: 7, bonus: 20 } },
      })
      getPoints.mockResolvedValue({ data: { data: POINTS } })
      getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } })
      const result = await useGamificationStore.getState().doCheckin()
      expect(result?.bonus).toBe(20)
    })

    it('失败（409/40901 今日已打卡）→ 异常向上抛出（页面 catch 展示）', async () => {
      checkin.mockRejectedValue(new Error('今日已打卡'))
      await expect(useGamificationStore.getState().doCheckin()).rejects.toThrow('今日已打卡')
      // 失败时不联动刷新
      expect(getPoints).not.toHaveBeenCalled()
      expect(getCheckinCalendar).not.toHaveBeenCalled()
      expect(useGamificationStore.getState().isCheckingIn).toBe(false)
    })
  })
})
