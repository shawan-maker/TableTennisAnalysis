/**
 * 积分历史页（02-user/frontend.md §4.4）
 * 折线图 + 历史记录列表
 */
import { useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Empty } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function RatingHistoryPage() {
  const { t } = useTranslation()
  const { ratingHistory, ratingHistoryTotal, fetchRatingHistory } = useUserStore()

  useEffect(() => {
    fetchRatingHistory(1, 100) // 拉取足够数据用于折线图
  }, [])

  // 构建折线图数据
  const chartData = [...ratingHistory].reverse() // 按时间正序排列

  // 计算折线图坐标
  const maxRating = Math.max(...chartData.map((d) => d.rating), 1500)
  const minRating = Math.min(...chartData.map((d) => d.rating), 1400)
  const range = maxRating - minRating || 100

  const chartWidth = 320
  const chartHeight = 180
  const padding = 20
  const pointSpacing = chartData.length > 1
    ? (chartWidth - padding * 2) / (chartData.length - 1)
    : 0

  const points = chartData.map((d, i) => ({
    x: padding + i * pointSpacing,
    y: chartHeight - padding - ((d.rating - minRating) / range) * (chartHeight - padding * 2),
    rating: d.rating,
    date: d.recorded_at,
  }))

  return (
    <ScrollView scrollY className="rating-history-page">
      {/* 折线图 */}
      <View className="chart-section">
        <View className="section-title">{t('user.ratingChart')}</View>
        {chartData.length > 0 ? (
          <View className="chart-container">
            {/* 简化实现：用 View 组件模拟折线图（weapp 不支持 SVG） */}
            <View className="svg-wrapper">
              <View className="chart-axis-y">
                <Text className="axis-label">{maxRating}</Text>
                <Text className="axis-label">{Math.round((maxRating + minRating) / 2)}</Text>
                <Text className="axis-label">{minRating}</Text>
              </View>
              <View className="chart-plot">
                {points.map((p, i) => (
                  <View
                    key={i}
                    className="chart-point"
                    style={{
                      left: `${(p.x / chartWidth) * 100}%`,
                      top: `${(p.y / chartHeight) * 100}%`,
                    }}
                  >
                    <Text className="point-value">{p.rating}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        ) : (
          <Empty description={t('user.noRatingHistory')} />
        )}
      </View>

      {/* 历史记录列表 */}
      <View className="history-list-section">
        <View className="section-title">
          {t('user.historyRecords')} ({ratingHistoryTotal})
        </View>
        {ratingHistory.map((item) => (
          <View key={item.id} className="history-item">
            <View className="item-info">
              <Text className="item-rating">{item.rating}</Text>
              <Text className="item-source">
                {item.source === 'manual' ? t('user.sourceManual') : t('user.sourceKqs')}
              </Text>
            </View>
            <Text className="item-date">
              {new Date(item.recorded_at).toLocaleDateString()}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  )
}
