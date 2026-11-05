/**
 * 图表数据变换纯函数（06-data_dashboard §4.3 / 08-progress_analysis §4.3）
 * weapp 端 CSS 折线图（数据点 + 旋转线段）的坐标计算，与 ECharts 无关的纯数据层
 */
import type { TrendSeries } from '@/services/dashboard'
import type { TrendHistoryPoint } from '@/services/progress'

/** CSS 折线图数据点（left/bottom 为 0-100 百分比定位） */
export interface ChartPoint {
  left: number
  bottom: number
  value: number
}

/** CSS 折线图线段（起点锚定 + 长度 + 角度） */
export interface ChartSegment {
  left: number
  bottom: number
  /** 线段宽度（百分比容器宽度对角线单位） */
  length: number
  /** 旋转角度（deg，CSS transform rotate 取负值） */
  angle: number
}

interface BuildLineChartOptions {
  /** 上下留白比例（防止点贴边裁切） */
  padding?: number
  /** 目标值参考线（null 则不画） */
  targetValue?: number | null
}

/**
 * 时间序列 → CSS 折线图坐标（点 + 连线段）。
 * 输出百分比坐标，容器用 position:relative + 100% 高度。
 */
export function buildLineChart(
  history: TrendHistoryPoint[] | number[],
  options: BuildLineChartOptions = {}
): { points: ChartPoint[]; segments: ChartSegment[]; targetLineBottom: number | null; minVal: number; maxVal: number } {
  const { padding = 0.1, targetValue = null } = options
  const values = history.map((h) => (typeof h === 'number' ? h : h.value))
  const points: ChartPoint[] = []
  const segments: ChartSegment[] = []

  if (values.length === 0) {
    return { points, segments, targetLineBottom: null, minVal: 0, maxVal: 0 }
  }

  const rawMin = Math.min(...values, targetValue ?? Infinity)
  const rawMax = Math.max(...values, targetValue ?? -Infinity)
  const range = rawMax - rawMin || 1
  // 上下各留 padding 比例的空白，避免点/值文本贴边
  const minVal = rawMin
  const maxVal = rawMax
  const span = 1 - padding * 2

  const toBottom = (v: number) => padding * 100 + ((v - minVal) / range) * span * 100
  const toLeft = (i: number) =>
    values.length > 1 ? (i / (values.length - 1)) * 100 : 50

  values.forEach((v, i) => {
    points.push({
      left: toLeft(i),
      bottom: toBottom(v),
      value: v,
    })
  })

  for (let i = 1; i < points.length; i++) {
    const p0 = points[i - 1]
    const p1 = points[i]
    // 容器宽高比未知，线段长度按百分比坐标的欧氏距离近似（CSS 宽度以容器宽度为 100%）
    const dx = p1.left - p0.left
    const dy = p1.bottom - p0.bottom
    const angle = Math.atan2(dy, dx) * (180 / Math.PI)
    const length = Math.sqrt(dx * dx + dy * dy)
    segments.push({
      left: p0.left,
      bottom: p0.bottom,
      length,
      // CSS bottom 轴向上为正，rotate 正向顺时针 → 折线下降时 dy<0 需负角
      angle: -angle,
    })
  }

  const targetBottom =
    targetValue == null ? null : Math.min(100, Math.max(0, toBottom(targetValue)))

  return { points, segments, targetLineBottom: targetBottom, minVal, maxVal }
}

/** 战绩趋势：按索引取胜率序列（series[0]=胜率，series[1]=比赛场次；后端固定顺序） */
export function extractWinRates(series: TrendSeries[]): number[] {
  return series[0]?.data ?? []
}

/** 战绩趋势：按索引取比赛场次序列 */
export function extractMatchCounts(series: TrendSeries[]): number[] {
  return series[1]?.data ?? []
}

/** 百分比格式化（0-1 浮点 → "56%"；null → "-"） */
export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-'
  return `${(value * 100).toFixed(digits)}%`
}

/** 对比变化值格式化（±号 + 百分比） */
export function formatChange(change: number | null | undefined): string {
  if (change == null || Number.isNaN(change)) return '-'
  const sign = change > 0 ? '+' : ''
  return `${sign}${(change * 100).toFixed(1)}%`
}
