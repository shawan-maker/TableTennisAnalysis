/**
 * 报告列表页（03-video_analysis/frontend.md §4.4）
 * 下拉刷新（页面级）+ 分页 append + 空态引导开始分析
 *
 * FS3-P3 修正：设计样例 numberOfLines 为 RN 属性，weapp 无效，
 * 改用 CSS line-clamp 两行截断；FlatList 对应 ScrollView scrollY。
 */
import { useEffect } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { View, Text, ScrollView, Image } from '@tarojs/components'
import { Button, Empty } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

const PAGE_SIZE = 20

export default function ReportListPage() {
  const { t } = useTranslation()
  const reports = useVideoAnalysisStore((s) => s.reports)
  const reportsTotal = useVideoAnalysisStore((s) => s.reportsTotal)
  const fetchReports = useVideoAnalysisStore((s) => s.fetchReports)
  const appendReports = useVideoAnalysisStore((s) => s.appendReports)

  // 初始加载
  useEffect(() => {
    fetchReports(1, PAGE_SIZE)
  }, [fetchReports])

  // 下拉刷新（index.config.ts enablePullDownRefresh）
  usePullDownRefresh(() => {
    fetchReports(1, PAGE_SIZE).finally(() => Taro.stopPullDownRefresh())
  })

  const handleReportClick = (reportId: number) => {
    Taro.navigateTo({ url: `/pages/video-analysis/report/index?report_id=${reportId}` })
  }

  const handleLoadMore = () => {
    if (reports.length < reportsTotal) {
      appendReports(Math.floor(reports.length / PAGE_SIZE) + 1, PAGE_SIZE)
    }
  }

  const hasMore = reports.length < reportsTotal

  return (
    <ScrollView scrollY className="report-list-page">
      <View className="page-header">
        <Text className="page-title">{t('analysis.myReports')}</Text>
        <Text className="page-count">{reportsTotal}</Text>
      </View>

      {reports.length === 0 && reportsTotal === 0 ? (
        <View className="empty-state">
          <Empty description={t('analysis.noReports')} />
          <Button
            type="primary"
            onClick={() => Taro.navigateTo({ url: '/pages/video-analysis/upload/index' })}
          >
            {t('analysis.startAnalysis')}
          </Button>
        </View>
      ) : (
        <View className="report-list">
          {reports.map((report) => (
            <View
              key={report.id}
              className="report-card"
              onClick={() => handleReportClick(report.id)}
            >
              {report.cover_image_url ? (
                <Image
                  className="report-cover"
                  src={report.cover_image_url}
                  mode="aspectFill"
                  alt={report.report_summary || t('home.reportDefaultTitle')}
                />
              ) : (
                <View className="report-cover-placeholder">
                  <Text aria-hidden="true">📊</Text>
                </View>
              )}
              <View className="report-info">
                <Text className="report-date">
                  {report.created_at ? new Date(report.created_at).toLocaleDateString() : ''}
                </Text>
                <Text className="report-summary">
                  {report.report_summary || t('analysis.noSummary')}
                </Text>
                {report.is_llm_generated && <Text className="ai-tag">{t('analysis.aiGenerated')}</Text>}
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 上拉加载更多 */}
      {hasMore && (
        <View className="load-more" onClick={handleLoadMore}>
          <Text>{t('common.loadMore')}</Text>
        </View>
      )}
    </ScrollView>
  )
}
