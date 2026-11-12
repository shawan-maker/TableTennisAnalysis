/**
 * progress_analysis 状态管理（08-progress_analysis/frontend.md §3）
 *
 * FS4-P3 契约修正（以后端为准）：
 * - trendDetail: 404/40415（无效指标）错误保留在 trendDetailError，页面渲染「指标不存在」分支
 * - problemChanges item 为结构化对象（ProblemChangeItem），渲染用 problem_name
 *
 * R-FE-R1 批次B（FE-P2-18）：除 trendDetail（页面级 error state 渲染引导分支）外，
 * 各 fetch catch 恢复失败 Toast 提示（common.operationFailed，trainingStore 同先例）。
 */
import Taro from '@tarojs/taro'
import i18next from 'i18next'
import { create } from 'zustand'
import * as progressApi from '@/services/progress'
import type {
  MetricTrend,
  TrendDetail,
  ComparisonData,
  SummaryData,
  ProblemChangeItem,
  SnapshotItem,
} from '@/services/progress'

export type { MetricTrend, TrendDetail, ComparisonData, SummaryData, ProblemChangeItem, SnapshotItem }

interface ProgressState {
  // 快照列表
  snapshots: SnapshotItem[]
  snapshotTotal: number
  // 趋势
  trends: MetricTrend[]
  trendDetail: TrendDetail | null
  /** 404/40415 无效指标 / 其他错误信息 */
  trendDetailError: string | null
  // 对比
  comparison: ComparisonData | null
  // 摘要
  summary: SummaryData | null
  // 问题变化
  problemChanges: { new: ProblemChangeItem[]; resolved: ProblemChangeItem[]; persistent: ProblemChangeItem[] } | null
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
  trendDetailError: null,
  comparison: null,
  summary: null,
  problemChanges: null,
  loading: false,

  fetchSnapshots: async (period?: string) => {
    set({ loading: true })
    try {
      const res = await progressApi.listSnapshots({ period, page: 1, page_size: 50 })
      const data = res.data.data
      set({ snapshots: data.items, snapshotTotal: data.total })
    } catch (err: any) {
      console.error('Failed to fetch snapshots:', err)
      Taro.showToast({ title: i18next.t('common.operationFailed'), icon: 'none' })
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
      console.error('Failed to fetch trends:', err)
      Taro.showToast({ title: i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },

  fetchTrendDetail: async (metric: string) => {
    set({ loading: true, trendDetail: null, trendDetailError: null })
    try {
      const res = await progressApi.getTechniqueTrendDetail(metric)
      set({ trendDetail: res.data.data })
    } catch (err: any) {
      // 404/40415 无效指标（R14-B4-1）——页面渲染「指标不存在」分支并引导返回
      set({ trendDetailError: err?.message || '指标不存在' })
    } finally {
      set({ loading: false })
    }
  },

  fetchComparison: async (reportA: number, reportB: number) => {
    set({ loading: true })
    try {
      const res = await progressApi.getComparison(reportA, reportB)
      set({ comparison: res.data.data })
    } catch (err: any) {
      console.error('Failed to fetch comparison:', err)
      Taro.showToast({ title: i18next.t('common.operationFailed'), icon: 'none' })
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
      console.error('Failed to fetch summary:', err)
      Taro.showToast({ title: i18next.t('common.operationFailed'), icon: 'none' })
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
      console.error('Failed to fetch problem changes:', err)
      Taro.showToast({ title: i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ loading: false })
    }
  },
}))
