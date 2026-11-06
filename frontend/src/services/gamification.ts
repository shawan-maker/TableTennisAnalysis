/**
 * gamification 模块 API Service（09-gamification/frontend.md §2）
 * 端点与后端 app/api/v1/gamification/router.py 逐字一致（4 个）。
 */
import request from './request'

/** 训练积分 */
export interface PointsData {
  total_points: number
  monthly_points: number
  current_streak: number
  /** streak>=3 时为 🔥，否则为空串（后端 R12-Gam-2 阈值 3） */
  streak_icon: string
}

/** 单日打卡记录 */
export interface CheckInDay {
  date: string
  checked_in: boolean
  type: string | null
}

/** 打卡日历 */
export interface CheckInCalendarData {
  year: number
  month: number
  days: CheckInDay[]
  monthly_checkin_count: number
  streak_days: number
}

/** 打卡结果（bonus 无奖励时为 null，R6-Gami-2） */
export interface CheckInResult {
  points_earned: number
  current_streak: number
  bonus: number | null
}

/** 已获得徽章 */
export interface BadgeEarned {
  badge_id: string
  name: string
  icon: string
  earned_at: string
}

/** 未获得徽章 */
export interface BadgeLocked {
  badge_id: string
  name: string
  icon: string
  progress: number
  target: number
}

/** 徽章列表 */
export interface BadgeListData {
  earned: BadgeEarned[]
  locked: BadgeLocked[]
}

/** WS badge_unlocked 事件条目（后端 check_badges newly_unlocked） */
export interface BadgeUnlockedItem {
  badge_id: string
  name: string
  icon: string
}

/** 获取训练积分（API §10.1）。 */
export function getPoints() {
  return request.get<PointsData>('/gamification/points')
}

/**
 * 获取打卡日历（API §10.2；不传年月则后端取当月）。
 * @param year - 年
 * @param month - 月
 */
export function getCheckinCalendar(year?: number, month?: number) {
  const params: Record<string, number> = {}
  if (year) params.year = year
  if (month) params.month = month
  return request.get<CheckInCalendarData>('/gamification/checkin-calendar', params)
}

/** 手动打卡（API §10.3，1/day 限流；409/40901 今日已打卡）。 */
export function checkin() {
  return request.post<CheckInResult>('/gamification/checkin')
}

/** 获取徽章列表（已获得/未获得，API §10.4）。 */
export function getBadges() {
  return request.get<BadgeListData>('/gamification/badges')
}
