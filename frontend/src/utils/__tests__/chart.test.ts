/**
 * utils/chart 图表数据变换用例（04-前端实施计划.md FS4「图表数据变换用例」）
 * - buildLineChart：坐标计算（padding 边界/单点/空序列/目标参考线）
 * - extractWinRates / extractMatchCounts：按索引取后端固定序列
 * - formatPercent / formatChange：百分比与变化值格式化
 */
import {
  buildLineChart,
  extractWinRates,
  extractMatchCounts,
  formatPercent,
  formatChange,
} from '@/utils/chart'

describe('buildLineChart 坐标计算', () => {
  it('空序列 → 空点/空线段/无目标线', () => {
    const r = buildLineChart([])
    expect(r.points).toHaveLength(0)
    expect(r.segments).toHaveLength(0)
    expect(r.targetLineBottom).toBeNull()
  })

  it('单点 → left 居中(50%) + 无线段', () => {
    const r = buildLineChart([{ date: '2026-11-05', value: 0.5 }])
    expect(r.points).toHaveLength(1)
    expect(r.points[0].left).toBe(50)
    expect(r.segments).toHaveLength(0)
  })

  it('两点上升序列 → 底部坐标递增 + 1 条线段（负角度）', () => {
    const r = buildLineChart([
      { date: '2026-11-04', value: 0.2 },
      { date: '2026-11-05', value: 0.6 },
    ])
    expect(r.points[0].bottom).toBeLessThan(r.points[1].bottom)
    expect(r.segments).toHaveLength(1)
    // 上升（bottom 增大）→ CSS rotate 角为负（rotate(-angle)）
    expect(r.segments[0].angle).toBeLessThan(0)
    expect(r.segments[0].left).toBe(r.points[0].left)
    expect(r.segments[0].bottom).toBe(r.points[0].bottom)
  })

  it('两端点不贴边（padding 10% → 首末点 bottom 在 10-90 区间）', () => {
    const r = buildLineChart([1, 2, 3])
    expect(r.points[0].bottom).toBeGreaterThanOrEqual(10)
    expect(r.points[2].bottom).toBeLessThanOrEqual(90)
  })

  it('目标参考线：目标值高于序列 → targetLineBottom 高于全部数据点', () => {
    const r = buildLineChart([1, 2], { targetValue: 3 })
    expect(r.targetLineBottom).not.toBeNull()
    expect(r.targetLineBottom!).toBeGreaterThan(r.points[1].bottom)
  })

  it('目标值等于序列最大值 → 参考线与最高点同高', () => {
    const r = buildLineChart([1, 2], { targetValue: 2 })
    expect(r.targetLineBottom).toBeCloseTo(r.points[1].bottom, 5)
  })

  it('值全相同（range=1 兜底）→ 不产生 NaN 坐标', () => {
    const r = buildLineChart([5, 5, 5])
    r.points.forEach((p) => {
      expect(Number.isNaN(p.bottom)).toBe(false)
      expect(Number.isNaN(p.left)).toBe(false)
    })
  })
})

describe('extractWinRates / extractMatchCounts（后端固定序列顺序）', () => {
  const series = [
    { name: '胜率', data: [0.5, 0.6] },
    { name: '比赛场次', data: [2, 5] },
  ]

  it('extractWinRates → series[0]', () => {
    expect(extractWinRates(series)).toEqual([0.5, 0.6])
  })

  it('extractMatchCounts → series[1]', () => {
    expect(extractMatchCounts(series)).toEqual([2, 5])
  })

  it('空序列数组 → 空数组兜底', () => {
    expect(extractWinRates([])).toEqual([])
    expect(extractMatchCounts([])).toEqual([])
  })
})

describe('formatPercent / formatChange', () => {
  it('formatPercent：0-1 → 百分号字符串', () => {
    expect(formatPercent(0.561)).toBe('56%')
    expect(formatPercent(0.5678, 1)).toBe('56.8%')
  })

  it('formatPercent：null/undefined → "-"', () => {
    expect(formatPercent(null)).toBe('-')
    expect(formatPercent(undefined)).toBe('-')
  })

  it('formatChange：正值带 + 号，负值原样，null → "-"', () => {
    expect(formatChange(0.05)).toBe('+5.0%')
    expect(formatChange(-0.05)).toBe('-5.0%')
    expect(formatChange(0)).toBe('0.0%')
    expect(formatChange(null)).toBe('-')
  })
})
