# progress_analysis 模块 — 前端垂直切片设计

> **模块名称**：`progress_analysis`
> **前端目录**：`frontend/src/pages/progress/` + `frontend/src/services/progress.ts` + `frontend/src/stores/progressStore.ts`
> **定位**：报告对比页（两次报告并排对比 6 维度）、趋势详情页（单项指标时间序列折线图）、进度综合摘要页
> **依据**：前端需求与界面设计 v2.0、API 详细设计 v1.3 §9

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §2.2 L1（我的 Tab → 训练报告 / 进度分析入口）
- [ ] 阅读本模块的 API 契约（§9.1-9.6，6 个端点）
- [ ] 阅读设计系统规范（色彩 `#E63946`/`#1D3557`/`#F4A261`/`#2A9D8F`，8px 间距网格）
- [ ] 确认本切片范围：报告对比页 + 趋势详情页 + 进度综合摘要页 + progressStore

---

## 2. API Service 模块

```typescript
// frontend/src/services/progress.ts
import request from './request'

/** 指标定义类型 */
export interface MetricDefinition {
  metric: string
  metric_name: string
  current_value: number | null
  previous_value: number | null
  change_rate: number | null
  trend: string | null
  target: number | null
  target_progress: number | null
  persistence_count: number
}

/** 趋势历史数据点 */
export interface TrendHistoryPoint {
  date: string
  value: number
}

/**
 * 获取进度快照列表。
 * @param params.period - 时间范围：month/quarter/year/all
 * @param params.page - 页码
 * @param params.page_size - 每页条数
 */
export function listSnapshots(params?: {
  period?: string
  page?: number
  page_size?: number
}) {
  return request.get('/progress/snapshots', params)
}

/**
 * 获取全部技术指标趋势。
 */
export function getTechniqueTrends() {
  return request.get('/progress/technique-trends')
}

/**
 * 获取单项指标趋势详情（含时间序列数据）。
 * @param metric - 指标名，如 backhand_ratio
 */
export function getTechniqueTrendDetail(metric: string) {
  return request.get(`/progress/technique-trends/${metric}`)
}

/**
 * 两次分析报告对比。
 * @param reportA - 报告 A ID
 * @param reportB - 报告 B ID
 */
export function getComparison(reportA: number, reportB: number) {
  return request.get('/progress/comparison', { report_a: reportA, report_b: reportB })
}

/**
 * 获取进度综合摘要。
 */
export function getSummary() {
  return request.get('/progress/summary')
}

/**
 * 获取问题变化列表（新增/已解决/持续）。
 */
export function getProblemChanges() {
  return request.get('/progress/problem-changes')
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/progressStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import i18next from 'i18next'
import * as progressApi from '@/services/progress'

interface SnapshotItem {
  id: number
  report_id: number
  created_at: string
  metrics_snapshot: Record<string, number | null>
}

interface MetricTrend {
  metric: string
  metric_name: string
  current_value: number | null
  previous_value: number | null
  change_rate: number | null
  trend: string | null
  target: number | null
  target_progress: number | null
  persistence_count: number
}

interface TrendDetail {
  metric: string
  metric_name: string
  current_value: number | null
  target_value: number | null
  target_progress: number | null
  trend: string | null
  change_rate: number | null
  persistence_count: number
  history: { date: string; value: number }[]
}

interface ComparisonData {
  report_a: { id: number; created_at: string }
  report_b: { id: number; created_at: string }
  comparisons: {
    technique_stats: Record<string, { a: number; b: number; change: number }>
    landing: Record<string, { a: number; b: number; change: number }>
    rally: { avg_length_a: number; avg_length_b: number; change: number }
    ball_speed: { avg_a: number; avg_b: number; change: number }
    score_analysis: { win_rate_a: number; win_rate_b: number; change: number }
    problem_changes: { new: string[]; resolved: string[]; persistent: string[] }
  }
}

interface SummaryData {
  summary_period: string
  total_analyses: number
  overall_progress: string
  metric_trends: MetricTrend[]
  problem_changes: { resolved: string[]; new: string[]; persistent: string[] }
  forecast: Record<string, {
    predicted_weeks_to_target: number | null
    confidence: string
    r_squared: number
  }>
}

interface ProgressState {
  // 快照列表
  snapshots: SnapshotItem[]
  snapshotTotal: number
  // 趋势
  trends: MetricTrend[]
  trendDetail: TrendDetail | null
  // 对比
  comparison: ComparisonData | null
  // 摘要
  summary: SummaryData | null
  // 问题变化
  problemChanges: { new: any[]; resolved: any[]; persistent: any[] } | null
  // 加载状态
  loading: boolean

  // Actions
  fetchSnapshots: (period?: string) => Promise<void>
  fetchTrends: () => Promise<void>
  fetchTrendDetail: (metric: string) => Promise<void>
  fetchComparison: (reportA: number, reportB: number) => Promise<void>
  fetchSummary: () => Promise<void>
  fetchProblemChanges: () => Promise<void>
}

export const useProgressStore = create<ProgressState>((set) => ({
  snapshots: [],
  snapshotTotal: 0,
  trends: [],
  trendDetail: null,
  comparison: null,
  summary: null,
  problemChanges: null,
  loading: false,

  fetchSnapshots: async (period) => {
    set({ loading: true })
    try {
      const res = await progressApi.listSnapshots({ period, page: 1, page_size: 50 })
      const data = res.data.data
      set({ snapshots: data.items, snapshotTotal: data.total })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchTrends: async () => {
    set({ loading: true })
    try {
      const res = await progressApi.getTechniqueTrends()
      set({ trends: res.data.data.metrics })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchTrendDetail: async (metric) => {
    set({ loading: true })
    try {
      const res = await progressApi.getTechniqueTrendDetail(metric)
      set({ trendDetail: res.data.data })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchComparison: async (reportA, reportB) => {
    set({ loading: true })
    try {
      const res = await progressApi.getComparison(reportA, reportB)
      set({ comparison: res.data.data })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchSummary: async () => {
    set({ loading: true })
    try {
      const res = await progressApi.getSummary()
      set({ summary: res.data.data })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchProblemChanges: async () => {
    set({ loading: true })
    try {
      const res = await progressApi.getProblemChanges()
      set({ problemChanges: res.data.data })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },
}))
```

---

## 4. 页面组件

### 4.1 进度综合摘要页

```tsx
// frontend/src/pages/progress/summary.tsx
import { useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Tag, Progress, Skeleton } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { useTranslation } from 'react-i18next'
import './summary.scss'

/** 趋势标签颜色映射 */
const TREND_COLORS: Record<string, string> = {
  improving: 'var(--color-success)',
  stagnant: 'var(--color-accent)',
  declining: 'var(--color-primary)',
  achieved: 'var(--color-secondary)',
  new: 'var(--color-primary)',
  resolved: 'var(--color-success)',
}

export default function ProgressSummary() {
  const { t } = useTranslation()
  const { summary, loading, fetchSummary } = useProgressStore()

  useEffect(() => {
    fetchSummary()
  }, [])

  if (loading && !summary) {
    return <View className="progress-summary loading"><Skeleton rows={3} animated /></View>
  }

  if (!summary) {
    return (
      <View className="progress-summary empty">
        <Text className="empty-text">{t('progress.noData')}</Text>
      </View>
    )
  }

  return (
    <View className="progress-summary">
      {/* 概览卡片区 */}
      <View className="summary-header">
        <Text className="summary-period">
          {t('progress.summaryPeriod')}: {t(`progress.period.${summary.summary_period}`)}
        </Text>
        <View className="summary-stats">
          <View className="stat-item">
            <Text className="stat-value">{summary.total_analyses}</Text>
            <Text className="stat-label">{t('progress.totalAnalyses')}</Text>
          </View>
          <View className="stat-item">
            <Tag
              type="primary"
              style={{ background: TREND_COLORS[summary.overall_progress] || 'var(--color-secondary)' }}
            >
              {t(`progress.trend.${summary.overall_progress}`)}
            </Tag>
            <Text className="stat-label">{t('progress.overallProgress')}</Text>
          </View>
        </View>
      </View>

      {/* 指标趋势卡片区 */}
      <View className="section">
        <Text className="section-title">{t('progress.metricTrends')}</Text>
        {summary.metric_trends.map((mt) => (
          <Cell
            key={mt.metric}
            title={mt.metric_name}
            description={`${t('progress.currentValue')}: ${mt.current_value ?? '-'} → ${t('progress.target')}: ${mt.target ?? '-'}`}
            onClick={() => {
              Taro.navigateTo({
                url: `/pages/progress/trend-detail/index?metric=${mt.metric}`,
              })
            }}
            extra={
              <View className="trend-extra">
                {mt.trend && (
                  <Tag style={{ background: TREND_COLORS[mt.trend] || 'var(--color-text-secondary)', color: 'var(--color-text-inverse)' }}>
                    {t(`progress.trend.${mt.trend}`)}
                  </Tag>
                )}
                {mt.target_progress != null && (
                  <Progress
                    percentage={mt.target_progress}
                    color={TREND_COLORS[mt.trend] || 'var(--color-accent)'}
                    size="small"
                  />
                )}
              </View>
            }
          />
        ))}
      </View>

      {/* 问题变化区 */}
      <View className="section">
        <Text className="section-title">{t('progress.problemChanges')}</Text>
        <View className="problem-group">
          <Text className="problem-label problem-new">
            {t('progress.newProblems')} ({summary.problem_changes.new.length})
          </Text>
          {summary.problem_changes.new.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
        <View className="problem-group">
          <Text className="problem-label problem-resolved">
            {t('progress.resolvedProblems')} ({summary.problem_changes.resolved.length})
          </Text>
          {summary.problem_changes.resolved.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
        <View className="problem-group">
          <Text className="problem-label problem-persistent">
            {t('progress.persistentProblems')} ({summary.problem_changes.persistent.length})
          </Text>
          {summary.problem_changes.persistent.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
      </View>

      {/* 预测区 */}
      {Object.keys(summary.forecast).length > 0 && (
        <View className="section">
          <Text className="section-title">{t('progress.forecast')}</Text>
          {Object.entries(summary.forecast).map(([metric, fc]) => (
            <Cell
              key={metric}
              title={metric}
              description={`${t('progress.predictedWeeks')}: ${fc.predicted_weeks_to_target ?? '-'}`}
              extra={
                <Tag style={{ background: fc.confidence === 'high' ? 'var(--color-success)' : 'var(--color-accent)', color: 'var(--color-text-inverse)' }}>
                  R²={fc.r_squared.toFixed(2)}
                </Tag>
              }
            />
          ))}
        </View>
      )}
    </View>
  )
}
```

### 4.2 报告对比页

```tsx
// frontend/src/pages/progress/comparison.tsx
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Tag, Empty } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { listSnapshots } from '@/services/progress'
import { useTranslation } from 'react-i18next'
import './comparison.scss'

export default function Comparison() {
  const { t } = useTranslation()
  const router = useRouter()
  const { comparison, loading, fetchComparison } = useProgressStore()
  const [snapshots, setSnapshots] = useState<any[]>([])
  const [reportA, setReportA] = useState<number | undefined>(
    router.params.report_a ? Number(router.params.report_a) : undefined
  )
  const [reportB, setReportB] = useState<number | undefined>(
    router.params.report_b ? Number(router.params.report_b) : undefined
  )

  useEffect(() => {
    loadSnapshots()
  }, [])

  useEffect(() => {
    if (reportA && reportB && reportA !== reportB) {
      fetchComparison(reportA, reportB)
    }
  }, [reportA, reportB])

  const loadSnapshots = async () => {
    const res = await listSnapshots({ page: 1, page_size: 50 })
    setSnapshots(res.data.data.items)
  }

  /** 格式化变化值 */
  const formatChange = (change: number | null | undefined): string => {
    if (change === null || change === undefined) return '-'
    const sign = change > 0 ? '+' : ''
    return `${sign}${(change * 100).toFixed(1)}%`
  }

  /** 变化值颜色 */
  const changeColor = (change: number | null | undefined, positive: boolean): string => {
    if (change === null || change === undefined) return 'var(--color-text-secondary)'
    if (change === 0) return 'var(--color-text-secondary)'
    const isPositive = change > 0
    if (positive) {
      return isPositive ? 'var(--color-success)' : 'var(--color-danger)'
    } else {
      return isPositive ? 'var(--color-danger)' : 'var(--color-success)'
    }
  }

  return (
    <View className="comparison-page">
      {/* 报告选择区 */}
      <View className="report-selector">
        <Picker
          mode="selector"
          range={snapshots.map((s) => `${s.report_id} (${s.created_at.slice(0, 10)})`)}
          onChange={(e) => setReportA(snapshots[e.detail.value].report_id)}
        >
          <Cell title={t('progress.reportA')} value={reportA ? `#${reportA}` : t('progress.selectReport')} />
        </Picker>
        <Picker
          mode="selector"
          range={snapshots.map((s) => `${s.report_id} (${s.created_at.slice(0, 10)})`)}
          onChange={(e) => setReportB(snapshots[e.detail.value].report_id)}
        >
          <Cell title={t('progress.reportB')} value={reportB ? `#${reportB}` : t('progress.selectReport')} />
        </Picker>
        <Button
          type="primary"
          block
          disabled={!reportA || !reportB || reportA === reportB}
          loading={loading}
          onClick={() => reportA && reportB && fetchComparison(reportA, reportB)}
        >
          {t('progress.startComparison')}
        </Button>
      </View>

      {/* 对比结果区 */}
      {comparison ? (
        <View className="comparison-result">
          {/* 技术统计对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.techniqueStats')}</Text>
            {Object.entries(comparison.comparisons.technique_stats).map(([key, val]) => (
              <View key={key} className="comparison-row">
                <Text className="row-label">{t(`progress.metric.${key}`)}</Text>
                <View className="row-values">
                  <Text className="value-a">{(val.a * 100).toFixed(1)}%</Text>
                  <Text className="value-arrow">→</Text>
                  <Text className="value-b">{(val.b * 100).toFixed(1)}%</Text>
                  <Text style={{ color: changeColor(val.change, true) }}>
                    {formatChange(val.change)}
                  </Text>
                </View>
              </View>
            ))}
          </View>

          {/* 落点对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.landing')}</Text>
            {Object.entries(comparison.comparisons.landing).map(([key, val]) => (
              <View key={key} className="comparison-row">
                <Text className="row-label">{t(`progress.metric.${key}`)}</Text>
                <View className="row-values">
                  <Text className="value-a">{(val.a * 100).toFixed(1)}%</Text>
                  <Text className="value-arrow">→</Text>
                  <Text className="value-b">{(val.b * 100).toFixed(1)}%</Text>
                  <Text style={{ color: changeColor(val.change, true) }}>
                    {formatChange(val.change)}
                  </Text>
                </View>
              </View>
            ))}
          </View>

          {/* 回合对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.rally')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.avgRallyLength')}</Text>
              <View className="row-values">
                <Text className="value-a">{comparison.comparisons.rally.avg_length_a}</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{comparison.comparisons.rally.avg_length_b}</Text>
                <Text style={{ color: changeColor(comparison.comparisons.rally.change, true) }}>
                  {comparison.comparisons.rally.change > 0 ? '+' : ''}
                  {comparison.comparisons.rally.change}
                </Text>
              </View>
            </View>
          </View>

          {/* 球速对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.ballSpeed')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.avgBallSpeed')}</Text>
              <View className="row-values">
                <Text className="value-a">{comparison.comparisons.ball_speed.avg_a} m/s</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{comparison.comparisons.ball_speed.avg_b} m/s</Text>
                <Text style={{ color: changeColor(comparison.comparisons.ball_speed.change, true) }}>
                  {comparison.comparisons.ball_speed.change > 0 ? '+' : ''}
                  {comparison.comparisons.ball_speed.change}
                </Text>
              </View>
            </View>
          </View>

          {/* 得分对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.scoreAnalysis')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.winRate')}</Text>
              <View className="row-values">
                <Text className="value-a">{(comparison.comparisons.score_analysis.win_rate_a * 100).toFixed(0)}%</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{(comparison.comparisons.score_analysis.win_rate_b * 100).toFixed(0)}%</Text>
                <Text style={{ color: changeColor(comparison.comparisons.score_analysis.change, true) }}>
                  {formatChange(comparison.comparisons.score_analysis.change)}
                </Text>
              </View>
            </View>
          </View>

          {/* 问题变化对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.problemChanges')}</Text>
            <View className="problem-changes">
              <View className="problem-group">
                <Tag style={{ background: 'var(--color-danger)', color: 'var(--color-text-inverse)' }}>
                  {t('progress.newProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.new.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.new.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
              <View className="problem-group">
                <Tag style={{ background: 'var(--color-success)', color: 'var(--color-text-inverse)' }}>
                  {t('progress.resolvedProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.resolved.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.resolved.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
              <View className="problem-group">
                <Tag style={{ background: 'var(--color-warning)', color: 'var(--color-text-inverse)' }}>
                  {t('progress.persistentProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.persistent.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.persistent.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
            </View>
          </View>
        </View>
      ) : !loading ? (
        <Empty description={t('progress.selectTwoReports')} />
      ) : null}
    </View>
  )
}
```

### 4.3 趋势详情页

```tsx
// frontend/src/pages/progress/trend-detail.tsx
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Tag, Progress, Skeleton } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { useTranslation } from 'react-i18next'
import './trend-detail.scss'

/** 趋势标签颜色映射 */
const TREND_COLORS: Record<string, string> = {
  improving: 'var(--color-success)',
  stagnant: 'var(--color-accent)',
  declining: 'var(--color-primary)',
  achieved: 'var(--color-secondary)',
  new: 'var(--color-primary)',
  resolved: 'var(--color-success)',
}

export default function TrendDetail() {
  const { t } = useTranslation()
  const router = useRouter()
  const { trendDetail, loading, fetchTrendDetail } = useProgressStore()
  const metric = router.params.metric || ''

  useEffect(() => {
    if (metric) {
      fetchTrendDetail(metric)
    }
  }, [metric])

  if (loading && !trendDetail) {
    return <View className="trend-detail loading"><Skeleton rows={3} animated /></View>
  }

  if (!trendDetail) {
    return <View className="trend-detail empty">{t('progress.noData')}</View>
  }

  // 构建简易折线图数据（CSS 实现，避免引入额外图表库）
  const history = trendDetail.history
  const values = history.map((h) => h.value)
  const minVal = Math.min(...values, trendDetail.target_value || 0)
  const maxVal = Math.max(...values, trendDetail.target_value || 0)
  const range = maxVal - minVal || 1

  return (
    <View className="trend-detail">
      {/* 指标概览卡 */}
      <View className="detail-header">
        <Text className="detail-title">{trendDetail.metric_name}</Text>
        {trendDetail.trend && (
          <Tag style={{ background: TREND_COLORS[trendDetail.trend] || 'var(--color-text-secondary)', color: 'var(--color-text-inverse)' }}>
            {t(`progress.trend.${trendDetail.trend}`)}
          </Tag>
        )}
      </View>

      <View className="detail-stats">
        <Cell
          title={t('progress.currentValue')}
          value={trendDetail.current_value?.toFixed(4) ?? '-'}
        />
        <Cell
          title={t('progress.target')}
          value={trendDetail.target_value?.toFixed(4) ?? '-'}
        />
        {trendDetail.target_progress != null && (
          <View className="progress-bar">
            <Text className="progress-label">
              {t('progress.targetProgress')}: {trendDetail.target_progress}%
            </Text>
            <Progress
              percentage={trendDetail.target_progress}
              color={TREND_COLORS[trendDetail.trend] || 'var(--color-accent)'}
            />
          </View>
        )}
        <Cell
          title={t('progress.changeRate')}
          value={trendDetail.change_rate ? `${(trendDetail.change_rate * 100).toFixed(1)}%` : '-'}
        />
        <Cell
          title={t('progress.persistenceCount')}
          value={`${trendDetail.persistence_count}`}
        />
      </View>

      {/* 时间序列折线图（CSS 实现） */}
      <View className="chart-section">
        <Text className="chart-title">{t('progress.timeSeries')}</Text>
        <View className="line-chart">
          {/* 目标线 */}
          {trendDetail.target_value && (
            <View
              className="target-line"
              style={{
                bottom: `${((trendDetail.target_value - minVal) / range) * 100}%`,
              }}
            >
              <Text className="target-label">{t('progress.target')}</Text>
            </View>
          )}
          {/* 数据点 */}
          <View className="chart-points">
            {history.map((h, i) => {
              const left = (i / (history.length - 1 || 1)) * 100
              const bottom = ((h.value - minVal) / range) * 100
              return (
                <View
                  key={i}
                  className="data-point"
                  style={{ left: `${left}%`, bottom: `${bottom}%` }}
                >
                  <View className="point-dot" />
                  <Text className="point-value">{h.value.toFixed(3)}</Text>
                  <Text className="point-date">{h.date.slice(5)}</Text>
                </View>
              )
            })}
          </View>
          {/* 连线（使用 SVG 或简单 CSS 模拟） */}
          <View className="chart-line-container">
            {history.map((h, i) => {
              if (i === 0) return null
              const prev = history[i - 1]
              const left0 = ((i - 1) / (history.length - 1 || 1)) * 100
              const left1 = (i / (history.length - 1 || 1)) * 100
              const bottom0 = ((prev.value - minVal) / range) * 100
              const bottom1 = ((h.value - minVal) / range) * 100
              const dy = bottom1 - bottom0
              const dx = left1 - left0
              const angle = Math.atan2(-dy, dx) * (180 / Math.PI)
              const length = Math.sqrt(dx * dx + dy * dy)
              return (
                <View
                  key={i}
                  className="line-segment"
                  style={{
                    left: `${left0}%`,
                    bottom: `${bottom0}%`,
                    width: `${length}%`,
                    transform: `rotate(${-angle}deg)`,
                    transformOrigin: '0 0',
                  }}
                />
              )
            })}
          </View>
        </View>
      </View>
    </View>
  )
}
```

---

## 5. 样式

```scss
// frontend/src/pages/progress/summary.scss
.progress-summary {
  min-height: 100vh;
  padding: var(--spacing-md);
  background: var(--color-background);

  &.loading, &.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-secondary);
  }
}

.summary-header {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);

  .summary-period {
    font-size: 13px;
    color: var(--color-text-secondary);
    display: block;
    margin-bottom: var(--spacing-sm-md);
  }

  .summary-stats {
    display: flex;
    gap: var(--spacing-lg);

    .stat-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--spacing-xs);

      .stat-value {
        font-size: 24px;
        font-weight: bold;
        color: var(--color-primary);
      }

      .stat-label {
        font-size: 12px;
        color: var(--color-text-secondary);
      }
    }
  }
}

.section {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);

  .section-title {
    font-size: 15px;
    font-weight: bold;
    color: var(--color-text-primary);
    display: block;
    margin-bottom: var(--spacing-sm-md);
  }
}

.trend-extra {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--spacing-xs);
}

.problem-group {
  margin-bottom: var(--spacing-sm-md);

  .problem-label {
    font-size: 13px;
    font-weight: 500;
    display: block;
    margin-bottom: var(--spacing-xs);
  }

  .problem-new { color: var(--color-danger); }
  .problem-resolved { color: var(--color-success); }
  .problem-persistent { color: var(--color-warning); }

  .problem-item {
    font-size: 13px;
    color: var(--color-text-primary);
    display: block;
    padding: var(--spacing-xs) 0; /* P3-fix: 2px→var(--spacing-xs) */
  }
}
```

```scss
// frontend/src/pages/progress/comparison.scss
.comparison-page {
  min-height: 100vh;
  padding: var(--spacing-md);
  background: var(--color-background);
}

.report-selector {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);

  :global(.nut-button) {
    margin-top: var(--spacing-sm-md);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    border-radius: var(--radius-md);
    height: 44px;
  }
}

.comparison-result {
  .comparison-section {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-sm-md);

    .section-title {
      font-size: 15px;
      font-weight: bold;
      color: var(--color-primary);
      display: block;
      margin-bottom: var(--spacing-sm-md);
      padding-bottom: var(--spacing-sm);
      border-bottom: 1px solid var(--color-divider);
    }
  }

  .comparison-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-sm) 0;

    .row-label {
      font-size: 13px;
      color: var(--color-text-secondary);
      flex: 1;
    }

    .row-values {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);

      .value-a {
        font-size: 13px;
        color: var(--color-text-secondary);
      }

      .value-arrow {
        font-size: 13px;
        color: var(--color-text-secondary);
      }

      .value-b {
        font-size: 13px;
        font-weight: 500;
        color: var(--color-text-primary);
      }
    }
  }

  .problem-changes {
    .problem-group {
      margin-bottom: var(--spacing-sm-md);

      .problem-item {
        font-size: 13px;
        display: block;
        padding: var(--spacing-xs) 0; /* P3-fix: 2px→var(--spacing-xs) */
      }

      .empty-item {
        font-size: 12px;
        color: var(--color-text-secondary);
      }
    }
  }
}
```

```scss
// frontend/src/pages/progress/trend-detail.scss
.trend-detail {
  min-height: 100vh;
  padding: var(--spacing-md);
  background: var(--color-background);

  &.loading, &.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-secondary);
  }
}

.detail-header {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm-md);

  .detail-title {
    font-size: 18px;
    font-weight: bold;
    color: var(--color-primary);
  }
}

.detail-stats {
  background: var(--color-card);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
  overflow: hidden;

  .progress-bar {
    padding: var(--spacing-sm-md) var(--spacing-md);

    .progress-label {
      font-size: 13px;
      color: var(--color-text-secondary);
      display: block;
      margin-bottom: var(--spacing-sm);
    }
  }
}

.chart-section {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);

  .chart-title {
    font-size: 15px;
    font-weight: bold;
    color: var(--color-text-primary);
    display: block;
    margin-bottom: var(--spacing-md);
  }
}

.line-chart {
  position: relative;
  height: 200px;
  width: 100%;
  margin-top: var(--spacing-md);
  border-left: 1px solid var(--color-divider);
  border-bottom: 1px solid var(--color-divider);

  .target-line {
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    background: var(--color-warning);
    border-top: 1px dashed var(--color-warning);

    .target-label {
      position: absolute;
      right: 0;
      top: -16px;
      font-size: 12px;
      color: var(--color-warning);
    }
  }

  .chart-points {
    position: absolute;
    inset: 0;
  }

  .data-point {
    position: absolute;
    transform: translate(-50%, 50%);

    .point-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--color-primary);
      margin: 0 auto;
    }

    .point-value {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      text-align: center;
      margin-top: var(--spacing-xs);
    }

    .point-date {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      text-align: center;
    }
  }

  .chart-line-container {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  .line-segment {
    position: absolute;
    height: 1px;
    background: var(--color-primary);
    transform-origin: 0 0;
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 progress 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // ... 其他页面
    'pages/progress/summary/index',       // 新增：进度综合摘要
    'pages/progress/comparison/index',    // 新增：报告对比
    'pages/progress/trend-detail/index',  // 新增：趋势详情
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "progress": {
    "summaryPeriod": "统计周期",
    "totalAnalyses": "分析次数",
    "overallProgress": "整体进度",
    "metricTrends": "指标趋势",
    "problemChanges": "问题变化",
    "forecast": "趋势预测",
    "predictedWeeks": "预计还需（周）",
    "currentValue": "当前值",
    "target": "目标值",
    "targetProgress": "目标达成度",
    "changeRate": "变化率",
    "persistenceCount": "持续次数",
    "timeSeries": "时间序列",
    "noData": "暂无进度数据，完成 AI 分析后将自动生成",
    "newProblems": "新增问题",
    "resolvedProblems": "已解决",
    "persistentProblems": "持续存在",
    "none": "无",
    "reportA": "报告 A",
    "reportB": "报告 B",
    "selectReport": "选择报告",
    "selectTwoReports": "请选择两份报告进行对比",
    "startComparison": "开始对比",
    "techniqueStats": "技术统计",
    "landing": "落点分布",
    "rally": "回合分析",
    "ballSpeed": "球速分析",
    "scoreAnalysis": "得分分析",
    "avgRallyLength": "平均回合长度",
    "avgBallSpeed": "平均球速",
    "winRate": "胜率",
    "period": {
      "month": "近一月",
      "quarter": "近三月",
      "year": "近一年",
      "all": "全部",
      "recent": "近期",
      "last_3_months": "近三月",
      "no_data": "无数据"
    },
    "trend": {
      "improving": "改善中",
      "stagnant": "停滞",
      "declining": "退步",
      "achieved": "已达标",
      "new": "新问题",
      "resolved": "已解决"
    },
    "metric": {
      "backhand_ratio": "反手使用率",
      "forehand_ratio": "正手使用率",
      "serve_ratio": "发球使用率",
      "landing_forehand_pct": "正手区落点率",
      "landing_backhand_pct": "反手区落点率",
      "landing_middle_pct": "中路落点率"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "progress": {
    "summaryPeriod": "Period",
    "totalAnalyses": "Total Analyses",
    "overallProgress": "Overall Progress",
    "metricTrends": "Metric Trends",
    "problemChanges": "Problem Changes",
    "forecast": "Forecast",
    "predictedWeeks": "Weeks to Target",
    "currentValue": "Current",
    "target": "Target",
    "targetProgress": "Target Progress",
    "changeRate": "Change Rate",
    "persistenceCount": "Persistence",
    "timeSeries": "Time Series",
    "noData": "No progress data yet. Complete an AI analysis to generate.",
    "newProblems": "New Problems",
    "resolvedProblems": "Resolved",
    "persistentProblems": "Persistent",
    "none": "None",
    "reportA": "Report A",
    "reportB": "Report B",
    "selectReport": "Select Report",
    "selectTwoReports": "Select two reports to compare",
    "startComparison": "Compare",
    "techniqueStats": "Technique Stats",
    "landing": "Landing Distribution",
    "rally": "Rally Analysis",
    "ballSpeed": "Ball Speed",
    "scoreAnalysis": "Score Analysis",
    "avgRallyLength": "Avg Rally Length",
    "avgBallSpeed": "Avg Ball Speed",
    "winRate": "Win Rate",
    "period": {
      "month": "Last Month",
      "quarter": "Last Quarter",
      "year": "Last Year",
      "all": "All Time",
      "recent": "Recent",
      "last_3_months": "Last 3 Months",
      "no_data": "No Data"
    },
    "trend": {
      "improving": "Improving",
      "stagnant": "Stagnant",
      "declining": "Declining",
      "achieved": "Achieved",
      "new": "New",
      "resolved": "Resolved"
    },
    "metric": {
      "backhand_ratio": "Backhand Ratio",
      "forehand_ratio": "Forehand Ratio",
      "serve_ratio": "Serve Ratio",
      "landing_forehand_pct": "Forehand Landing",
      "landing_backhand_pct": "Backhand Landing",
      "landing_middle_pct": "Middle Landing"
    }
  }
}
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 摘要页布局符合设计系统（概览卡片 + 指标趋势列表 + 问题变化 + 预测）
- [ ] 趋势标签颜色正确：improving=`#2A9D8F`、stagnant=`#F4A261`、declining=`#E63946`、achieved=`#1D3557`
- [ ] 报告对比页：A/B 选择器 + 6 维度对比区域布局清晰
- [ ] 变化值颜色：改善=绿色 `#2A9D8F`、退步=红色 `#E63946`、不变=灰色
- [ ] 趋势详情页折线图正确渲染（数据点 + 连线 + 目标线）
- [ ] 空状态正确显示引导文字
- [ ] 进度条颜色与趋势标签一致

### 功能验证
- [ ] 摘要页：加载 → 显示整体进度 + 指标趋势列表 + 问题变化 + 预测
- [ ] 点击指标趋势项 → 跳转趋势详情页
- [ ] 趋势详情页：加载 → 显示当前值/目标/变化率 + 时间序列折线图
- [ ] 报告对比页：选择两份报告 → 点击对比 → 显示 6 维度对比结果
- [ ] 对比页：变化值正负方向正确、颜色正确
- [ ] 对比页：问题变化区分新增/已解决/持续
- [ ] 同一报告对比时按钮禁用

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量（`--color-primary` 等）
- **禁止** 安装新的 npm 包（图表用 CSS 实现，不引入图表库）
- **禁止** 跨用户访问数据（所有请求通过后端 JWT 鉴权）
- 趋势标签颜色 **必须** 与 6 种趋势类型映射一致
- 报告对比 **必须** 覆盖 6 个维度，**禁止** 遗漏维度
