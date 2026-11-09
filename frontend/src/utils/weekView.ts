/**
 * 打卡周视图派生纯函数（00-home/frontend.md §4.5 周视图数据变换）
 *
 * 后端 GET /gamification/checkin-calendar 返回**月历**结构
 * （year/month/days/monthly_checkin_count/streak_days），首页周视图由本模块
 * 从月历裁剪派生（FS7-P3：设计样例的 week_start/exp_earned 为臆造字段）。
 *
 * 时区约束（FS5 先例）：后端按 CST 计日，todayStr 用本地 y/m/d 构造，
 * 禁止 toISOString()（UTC 跨日偏移）。
 */
import type { CheckInCalendarData } from '@/services/gamification'

/** 周视图单日 */
export interface WeekViewDay {
  /** YYYY-MM-DD（周一~周日连续 7 天） */
  date: string
  /** 是否属于月历数据覆盖的月份（false = 跨月空格，月历无该日数据） */
  inMonth: boolean
  checked_in: boolean
  isToday: boolean
}

/** 周视图 */
export interface WeekView {
  /** 本周一日期 YYYY-MM-DD */
  weekStart: string
  /** 7 天（周一 → 周日） */
  days: WeekViewDay[]
  /** 连续打卡天数（月历 streak_days） */
  streakDays: number
  /** 今日是否已打卡 */
  todayCheckedIn: boolean
}

/** 本地日期串（YYYY-MM-DD，避免 toISOString UTC 跨日偏移） */
function localDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 从月历数据派生本周（周一~周日）周视图。
 * @param calendar - 当月打卡月历
 * @param todayStr - 可注入的"今天"日期串（缺省取本地今天，测试用）
 */
export function buildWeekView(calendar: CheckInCalendarData, todayStr?: string): WeekView {
  const today = todayStr ?? localDateStr(new Date())
  const [ty, tm, td] = today.split('-').map(Number)
  // 周一起始偏移：getDay() 周日=0 → (0+6)%7=6；周一=1 → 0
  const todayDow = new Date(ty, tm - 1, td).getDay()
  const monday = new Date(ty, tm - 1, td - ((todayDow + 6) % 7))

  // 月历 days 索引（key=日期串）
  const dayMap = new Map<string, boolean>()
  calendar.days.forEach((d) => dayMap.set(d.date, d.checked_in))

  const days: WeekViewDay[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i)
    const dateStr = localDateStr(d)
    const inMonth = dayMap.has(dateStr)
    days.push({
      date: dateStr,
      inMonth,
      checked_in: inMonth ? (dayMap.get(dateStr) as boolean) : false,
      isToday: dateStr === today,
    })
  }

  return {
    weekStart: localDateStr(monday),
    days,
    streakDays: calendar.streak_days,
    todayCheckedIn: dayMap.get(today) ?? false,
  }
}

export default buildWeekView
