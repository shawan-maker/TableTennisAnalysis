/**
 * 趋势详情页（08-progress_analysis/frontend.md §4.3）
 * 单项指标概览 + 目标线 + CSS 折线图（时间序列）
 *
 * 40415 分支（FS4 关键子任务）：metric 不在后端 METRIC_DEFINITIONS 时
 * GET /progress/technique-trends/{metric} 返回 404/40415「指标不存在」，
 * 页面渲染错误态并引导返回 summary。
 */
import { useEffect } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Tag, Progress, Button, Skeleton } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { useTranslation } from 'react-i18next'
import { buildLineChart } from '@/utils/chart'
import './index.scss'

/** 趋势标签颜色映射（§4.3） */
const TREND_COLORS: Record<string, string> = {
  improving: 'var(--color-success)',
  stagnant: 'var(--color-accent)',
  declining: 'var(--color-primary)',
  achieved: 'var(--color-secondary)',
  new: 'var(--color-primary)',
  resolved: 'var(--color-success)',
}

export default function TrendDetailPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const trendDetail = useProgressStore((s) => s.trendDetail)
  const trendDetailError = useProgressStore((s) => s.trendDetailError)
  const loading = useProgressStore((s) => s.loading)
  const fetchTrendDetail = useProgressStore((s) => s.fetchTrendDetail)
  const metric = (router.params.metric as string) || ''

  useEffect(() => {
    if (metric) {
      fetchTrendDetail(metric)
    }
  }, [metric, fetchTrendDetail])

  // 40415 无效指标分支（R14-B4-1）
  if (trendDetailError) {
    return (
      <View className="trend-detail error-state">
        <Text className="error-icon" aria-hidden="true">⚠️</Text>
        <Text className="error-text">{trendDetailError}</Text>
        <Button type="primary" block onClick={() => Taro.navigateBack()}>
          {t('common.back')}
        </Button>
      </View>
    )
  }

  if (loading && !trendDetail) {
    return (
      <View className="trend-detail loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  if (!trendDetail) {
    return (
      <View className="trend-detail empty">
        <Text className="empty-text">{t('progress.noData')}</Text>
      </View>
    )
  }

  // CSS 折线图坐标（utils/chart 纯函数，含目标参考线）
  const { points, segments, targetLineBottom } = buildLineChart(trendDetail.history, {
    targetValue: trendDetail.target_value,
  })

  return (
    <View className="trend-detail">
      {/* 指标概览卡 */}
      <View className="detail-header">
        <Text className="detail-title">{trendDetail.metric_name}</Text>
        {trendDetail.trend && (
          <Tag
            background={TREND_COLORS[trendDetail.trend] || 'var(--color-text-secondary)'}
            color="var(--color-text-inverse)"
          >
            {t(`progress.trend.${trendDetail.trend}`)}
          </Tag>
        )}
      </View>

      <View className="detail-stats">
        <Cell title={t('progress.currentValue')} extra={<Text>{trendDetail.current_value?.toFixed(4) ?? '-'}</Text>} />
        <Cell title={t('progress.target')} extra={<Text>{trendDetail.target_value?.toFixed(4) ?? '-'}</Text>} />
        {trendDetail.target_progress != null && (
          <View className="progress-bar">
            <Text className="progress-label">
              {t('progress.targetProgress')}: {trendDetail.target_progress}%
            </Text>
            <Progress
              percent={trendDetail.target_progress}
              color={TREND_COLORS[trendDetail.trend ?? ''] || 'var(--color-accent)'}
              strokeWidth="8px"
            />
          </View>
        )}
        <Cell
          title={t('progress.changeRate')}
          extra={
            <Text>
              {trendDetail.change_rate != null
                ? `${(trendDetail.change_rate * 100).toFixed(1)}%`
                : '-'}
            </Text>
          }
        />
        <Cell title={t('progress.persistenceCount')} extra={<Text>{trendDetail.persistence_count ?? '-'}</Text>} />
      </View>

      {/* 时间序列折线图（CSS 实现，含目标参考线） */}
      <View className="chart-section">
        <Text className="chart-title">{t('progress.timeSeries')}</Text>
        {trendDetail.history.length === 0 ? (
          <View className="chart-empty">
            <Text>{t('progress.noData')}</Text>
          </View>
        ) : (
          <View
            className="line-chart"
            role="img"
            aria-label={`${trendDetail.metric_name} ${t('progress.timeSeries')}: ${trendDetail.history
              .map((h) => `${h.date.slice(5)} ${h.value.toFixed(3)}`)
              .join(', ')}`}
          >
            {/* 目标参考线 */}
            {targetLineBottom != null && (
              <View className="target-line" style={{ bottom: `${targetLineBottom}%` }}>
                <Text className="target-label">{t('progress.target')}</Text>
              </View>
            )}
            {/* 连线 */}
            {segments.map((seg, i) => (
              <View
                key={`seg-${i}`}
                className="line-segment"
                style={{
                  left: `${seg.left}%`,
                  bottom: `${seg.bottom}%`,
                  width: `${seg.length}%`,
                  transform: `rotate(${seg.angle}deg)`,
                }}
              />
            ))}
            {/* 数据点 */}
            {points.map((p, i) => (
              <View
                key={`pt-${i}`}
                className="data-point"
                style={{ left: `${p.left}%`, bottom: `${p.bottom}%` }}
              >
                <View className="point-dot" />
                <Text className="point-value">{p.value.toFixed(3)}</Text>
                <Text className="point-date">{trendDetail.history[i].date.slice(5)}</Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </View>
  )
}
