/**
 * 数据看板首页（06-data_dashboard/frontend.md §4.1）
 * 概览卡片 + 战绩趋势折线 + 技术统计环形图 + 累计落点热图 + 比赛记录列表
 *
 * FS4-P3 修正：设计样例的 NutUI PullRefresh 在 weapp 与页面 ScrollView 嵌套易冲突，
 * 改用页面级下拉刷新（enablePullDownRefresh + Taro.usePullDownRefresh，FS3 list 页同先例）；
 * 图表按 weapp 端 CSS 方案实现（设计样例自注 SVG 为 H5 端、weapp 需替换）。
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
      <OverviewCards data={store.overview} loading={store.overviewLoading} />

      {/* 战绩趋势 */}
      <WinRateTrend
        data={store.winRateTrend}
        period={store.trendPeriod}
        loading={store.trendLoading}
        onPeriodChange={store.setTrendPeriod}
      />

      {/* 技术统计 */}
      <TechniqueStats data={store.techniqueStats} loading={store.techniqueLoading} />

      {/* 累计落点热图 */}
      <LandingHeatmap data={store.heatmap} loading={store.heatmapLoading} />

      {/* 比赛记录列表 */}
      <MatchRecordList
        items={store.matchRecords}
        total={store.matchTotal}
        filter={store.matchFilter}
        loading={store.matchLoading}
        hasMore={store.matchHasMore}
        onFilterChange={store.setMatchFilter}
        onLoadMore={store.loadMoreMatches}
      />
    </View>
  )
}
