/**
 * 最近分析报告卡片组件（00-home/frontend.md §4.6）
 * 缩略图 + 摘要 + 日期；空态引导上传。
 *
 * FS7-P3 契约同步：数据源 GET /video-analysis/reports 首条 ReportListItem
 * （report_summary / cover_image_url），设计样例的 title/status/overall_score/
 * thumbnail_url 字段为臆造（后端 ReportListItem 无这些字段）；
 * 跳转 FS3 报告详情 ?report_id=。
 */
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { ReportListItem } from '@/services/home'
import { DEFAULT_REPORT_THUMBNAIL } from '@/constants/home'
import './LatestReportCard.scss'

interface Props {
  report: ReportListItem | null
  loading: boolean
}

export default function LatestReportCard({ report, loading }: Props) {
  const { t } = useTranslation()

  const handleClick = () => {
    if (report) {
      Taro.navigateTo({ url: `/pages/video-analysis/report/index?report_id=${report.id}` })
    }
  }

  const handleUpload = () => {
    Taro.navigateTo({ url: '/pages/video-analysis/upload/index' })
  }

  return (
    <View className="latest-report">
      <Text className="section-title">🎬 {t('home.latestReport')}</Text>

      {loading ? (
        <View className="card-placeholder">
          <Skeleton rows={2} animated />
        </View>
      ) : report ? (
        <View className="report-card" onClick={handleClick}>
          <Image
            className="report-thumbnail"
            src={report.cover_image_url || DEFAULT_REPORT_THUMBNAIL}
            mode="aspectFill"
          />
          <View className="report-info">
            <Text className="report-title">
              {report.report_summary || t('home.reportDefaultTitle')}
            </Text>
            {report.created_at && (
              <Text className="report-date">
                {new Date(report.created_at).toLocaleDateString()}
              </Text>
            )}
          </View>
          <Text className="report-arrow">›</Text>
        </View>
      ) : (
        <View className="empty-report" onClick={handleUpload}>
          {/* NutUI 2.7.14 真实 API：Empty 用 title（FS5 先例） */}
          <Empty title={t('home.noReportYet')} />
          <Text className="upload-hint">{t('home.uploadFirst')}</Text>
        </View>
      )}
    </View>
  )
}
