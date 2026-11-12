/**
 * 数据看板首页（06-data_dashboard/frontend.md §4.1）
 * 概览卡片 + 战绩趋势折线 + 技术统计环形图 + 累计落点热图 + 比赛记录列表
 *
 * FS4-P3 修正：设计样例的 NutUI PullRefresh 在 weapp 与页面 ScrollView 嵌套易冲突，
 * 改用页面级下拉刷新（enablePullDownRefresh + Taro.usePullDownRefresh，FS3 list 页同先例）；
 * 图表按 weapp 端 CSS 方案实现（设计样例自注 SVG 为 H5 端、weapp 需替换）。
 *
 * R-FE-R1 批次B（FE-P2-16）：五区块错误态——store 各 fetch 失败置 error 标志，
 * 页面以区块级错误卡 + 重试按钮替代渲染（frontend.md L1460「网络错误显示错误提示」）。
 */
import { useEffect } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import { useDashboardStore } from '@/stores/dashboardStore'
import OverviewCards from './components/OverviewCards'
import WinRateTrend from './components/WinRateTrend'
import TechniqueStats from './components/TechniqueStats'
import LandingHeatmap from './components/LandingHeatmap'
import MatchRecordList from './components/MatchRecordList'
import './index.scss'

/** 区块级错误卡：提示文案 + 重试按钮（重试复用既有 fetch action，成功后 error 自动复位） */
function SectionError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <View className="section-error">
      <Text className="section-error-text">{t('dashboard.loadFailed')}</Text>
      <View className="section-error-btn" onClick={() => onRetry()}>
        <Text className="section-error-btn-text">{t('common.retry')}</Text>
      </View>
    </View>
  )
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const store = useDashboardStore()

  useEffect(() => {
    store.refreshAll()
  }, [])

  // 下拉刷新（页面级）
  usePullDownRefresh(() => {
    store.refreshAll().finally(() => Taro.stopPullDownRefresh())
  })

  return (
    <View className="dashboard-page">
      <View className="dashboard-header">
        <Text className="dashboard-title">{t('dashboard.title')}</Text>
      </View>

      {/* 概览卡片 */}
      {store.overviewError ? (
        <SectionError onRetry={store.fetchOverview} />
      ) : (
        <OverviewCards data={store.overview} loading={store.overviewLoading} />
      )}

      {/* 战绩趋势 */}
      {store.trendError ? (
        <SectionError onRetry={() => store.fetchWinRateTrend()} />
      ) : (
        <WinRateTrend
          data={store.winRateTrend}
          period={store.trendPeriod}
          loading={store.trendLoading}
          onPeriodChange={store.setTrendPeriod}
        />
      )}

      {/* 技术统计 */}
      {store.techniqueError ? (
        <SectionError onRetry={store.fetchTechniqueStats} />
      ) : (
        <TechniqueStats data={store.techniqueStats} loading={store.techniqueLoading} />
      )}

      {/* 累计落点热图 */}
      {store.heatmapError ? (
        <SectionError onRetry={store.fetchLandingHeatmap} />
      ) : (
        <LandingHeatmap data={store.heatmap} loading={store.heatmapLoading} />
      )}

      {/* 比赛记录列表 */}
      {store.matchError ? (
        <SectionError onRetry={() => store.fetchMatchRecords(true)} />
      ) : (
        <MatchRecordList
          items={store.matchRecords}
          total={store.matchTotal}
          filter={store.matchFilter}
          loading={store.matchLoading}
          hasMore={store.matchHasMore}
          onFilterChange={store.setMatchFilter}
          onLoadMore={store.loadMoreMatches}
        />
      )}
    </View>
  )
}
