/**
 * home 模块常量（00-home/frontend.md §7）
 */

/** 快捷操作宫格路由映射 */
export const QUICK_ROUTES = {
  aiAnalysis: '/pages/video-analysis/upload/index',
  manualEntry: '/pages/match-data/quick-entry/index',
  scoreboard: '/pages/scoring/setup/index',
  dataBoard: '/pages/dashboard/index',
} as const

/** 打卡日历周几 i18n key（周一起始） */
export const WEEKDAY_KEYS = [
  'home.weekMon',
  'home.weekTue',
  'home.weekWed',
  'home.weekThu',
  'home.weekFri',
  'home.weekSat',
  'home.weekSun',
] as const

/** 默认头像 */
export const DEFAULT_AVATAR = 'https://cdn.pingpongai.com/images/default-avatar.png'

/** 默认报告缩略图 */
export const DEFAULT_REPORT_THUMBNAIL = 'https://cdn.pingpongai.com/images/report-default.png'
