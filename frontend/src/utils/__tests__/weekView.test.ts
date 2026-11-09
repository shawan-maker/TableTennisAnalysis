/**
 * buildWeekView 纯函数测试（00-home/frontend.md §4.5 周视图派生，FS7）
 * - 周一锚定（周三/周日边界）
 * - 7 天连续 + isToday 唯一标记
 * - 月历覆盖判定（跨月 inMonth=false）
 * - todayCheckedIn / streakDays 透传
 */
import { buildWeekView } from '@/utils/weekView'
import type { CheckInCalendarData } from '@/services/gamification'

/** 构造月历：days 为 YYYY-MM-DD → checked_in 映射 */
function makeCalendar(year: number, month: number, checked: string[] = [], streak = 0): CheckInCalendarData {
  const days = Array.from({ length: 30 }, (_, i) => {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
    return { date, checked_in: checked.includes(date), type: null }
  })
  return { year, month, days, monthly_checkin_count: checked.length, streak_days: streak }
}

describe('buildWeekView 周一锚定', () => {
  it('today=周三(2026-11-04) → weekStart=2026-11-02（周一）', () => {
    const wv = buildWeekView(makeCalendar(2026, 11), '2026-11-04')
    expect(wv.weekStart).toBe('2026-11-02')
  })

  it('today=周日(2026-11-01) → weekStart=2026-10-26（本周一，非下周一）', () => {
    const wv = buildWeekView(makeCalendar(2026, 11), '2026-11-01')
    expect(wv.weekStart).toBe('2026-10-26')
  })

  it('today=周一(2026-11-02) → weekStart=当天', () => {
    const wv = buildWeekView(makeCalendar(2026, 11), '2026-11-02')
    expect(wv.weekStart).toBe('2026-11-02')
  })

  it('7 天连续递增（周一 → 周日）', () => {
    const wv = buildWeekView(makeCalendar(2026, 11), '2026-11-04')
    expect(wv.days).toHaveLength(7)
    expect(wv.days[0].date).toBe('2026-11-02')
    expect(wv.days[6].date).toBe('2026-11-08')
    for (let i = 1; i < 7; i++) {
      expect(wv.days[i].date > wv.days[i - 1].date).toBe(true)
    }
  })

  it('isToday 恰好 1 个且等于 todayStr', () => {
    const wv = buildWeekView(makeCalendar(2026, 11), '2026-11-04')
    expect(wv.days.filter((d) => d.isToday)).toHaveLength(1)
    expect(wv.days.find((d) => d.isToday)?.date).toBe('2026-11-04')
  })
})

describe('buildWeekView 月历覆盖判定', () => {
  it('today=周日 11-01：10-26~10-31 跨月 → inMonth=false / checked_in=false', () => {
    const wv = buildWeekView(makeCalendar(2026, 11, ['2026-11-01']), '2026-11-01')
    // 11 月月历只覆盖 11-01~11-30：前 6 天来自 10 月
    expect(wv.days[0].date).toBe('2026-10-26')
    expect(wv.days[0].inMonth).toBe(false)
    expect(wv.days[0].checked_in).toBe(false)
    expect(wv.days[6].inMonth).toBe(true)
    expect(wv.days[6].checked_in).toBe(true)
  })

  it('月历内日期 inMonth=true 且 checked_in 精确映射', () => {
    const wv = buildWeekView(makeCalendar(2026, 11, ['2026-11-02', '2026-11-04']), '2026-11-05')
    const byDate = new Map(wv.days.map((d) => [d.date, d]))
    expect(byDate.get('2026-11-02')?.inMonth).toBe(true)
    expect(byDate.get('2026-11-02')?.checked_in).toBe(true)
    expect(byDate.get('2026-11-03')?.checked_in).toBe(false)
    expect(byDate.get('2026-11-04')?.checked_in).toBe(true)
  })
})

describe('buildWeekView 透传字段', () => {
  it('streakDays 来自月历 streak_days', () => {
    const wv = buildWeekView(makeCalendar(2026, 11, [], 5), '2026-11-04')
    expect(wv.streakDays).toBe(5)
  })

  it('todayCheckedIn：月历含今日 checked_in=true', () => {
    const a = buildWeekView(makeCalendar(2026, 11, ['2026-11-04']), '2026-11-04')
    expect(a.todayCheckedIn).toBe(true)
    const b = buildWeekView(makeCalendar(2026, 11, []), '2026-11-04')
    expect(b.todayCheckedIn).toBe(false)
  })

  it('today 不在月历 days 中（跨月未覆盖）→ todayCheckedIn=false', () => {
    // 构造一个只含 1~3 号的"残缺"月历（极端防御：4 号无数据）
    const calendar: CheckInCalendarData = {
      year: 2026, month: 11,
      days: ['2026-11-01', '2026-11-02', '2026-11-03'].map((d) => ({ date: d, checked_in: false, type: null })),
      monthly_checkin_count: 0, streak_days: 0,
    }
    const wv = buildWeekView(calendar, '2026-11-04')
    expect(wv.todayCheckedIn).toBe(false)
  })
})
