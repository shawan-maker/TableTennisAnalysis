/**
 * dashboard 常量（06-data_dashboard/frontend.md §7 L1408-1431）
 * R-FE-R1 批次C（FE-P3-16）：PERIOD/RESULT_FILTER/GRID_CELL_LABELS 三组常量
 * 修复前内联在 WinRateTrend/MatchRecordList/LandingHeatmap 三组件，按设计收敛；
 * labelKey 统一走 i18n，组件内经 t() 派生 label。
 */
import type { TrendPeriod, ResultFilter } from '@/services/dashboard'

/** 战绩趋势时间周期选项（WinRateTrend Tabs） */
export const PERIOD_OPTIONS: Array<{ key: TrendPeriod; labelKey: string }> = [
  { key: 'month', labelKey: 'dashboard.month' },
  { key: 'quarter', labelKey: 'dashboard.quarter' },
  { key: 'year', labelKey: 'dashboard.year' },
]

/** 比赛记录结果筛选选项（MatchRecordList Tabs） */
export const RESULT_FILTER_OPTIONS: Array<{ key: ResultFilter; labelKey: string }> = [
  { key: 'all', labelKey: 'dashboard.allMatches' },
  { key: 'win', labelKey: 'dashboard.winsOnly' },
  { key: 'lose', labelKey: 'dashboard.lossesOnly' },
]

/** 九宫格标签键（LandingHeatmap，§7 GRID_CELL_LABELS 顺序） */
export const GRID_CELL_LABELS = [
  'dashboard.cell.leftShort', 'dashboard.cell.midShort', 'dashboard.cell.rightShort',
  'dashboard.cell.leftMid', 'dashboard.cell.midMid', 'dashboard.cell.rightMid',
  'dashboard.cell.leftLong', 'dashboard.cell.midLong', 'dashboard.cell.rightLong',
]
