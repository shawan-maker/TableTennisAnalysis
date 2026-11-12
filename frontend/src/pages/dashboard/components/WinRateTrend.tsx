/**
 * 战绩趋势折线图组件（06-data_dashboard/frontend.md §4.3）
 * month/quarter/year 时间筛选 + CSS 折线图（weapp 端方案，样例 SVG 为 H5 端）
 *
 * FS4-P3：series.name 为后端中文文案（「胜率」），按 i18n 匹配在英文环境失效，
 * 改按固定索引取数（series[0]=胜率、series[1]=比赛场次，utils/chart extractWinRates）。
 */
import { View, Text } from '@tarojs/components'
import { Tabs, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { WinRateTrendData, TrendPeriod } from '@/services/dashboard'
import { buildLineChart, extractWinRates } from '@/utils/chart'
import { PERIOD_OPTIONS } from '@/constants/dashboard'
import './WinRateTrend.scss'

interface Props {
  data: WinRateTrendData | null
  period: TrendPeriod
  loading: boolean
  onPeriodChange: (period: TrendPeriod) => void
}

export default function WinRateTrend({ data, period, loading, onPeriodChange }: Props) {
  const { t } = useTranslation()

  // R-FE-R1 批次C（FE-P3-16）：周期选项收敛至 constants/dashboard.ts（设计 L1408-1431）
  const periodOptions = PERIOD_OPTIONS.map((o) => ({ key: o.key, label: t(o.labelKey) }))

  const winRates = data ? extractWinRates(data.series) : []
  const { points, segments } = data ? buildLineChart(winRates) : { points: [], segments: [] }

  return (
    <View className="win-rate-trend">
      <View className="section-header">
        <Text className="section-title">📈 {t('dashboard.winRateTrend')}</Text>
      </View>

      <Tabs value={period} onChange={(val) => onPeriodChange(val as TrendPeriod)}>
        {periodOptions.map((opt) => (
          <Tabs.TabPane key={opt.key} title={opt.label} value={opt.key} />
        ))}
      </Tabs>

      {loading || !data ? (
        <Skeleton rows={3} animated />
      ) : data.labels.length === 0 ? (
        <View className="chart-empty">
          <Text>{t('dashboard.noMatchData')}</Text>
        </View>
      ) : (
        <View
          className="chart-container"
          role="img"
          aria-label={`${t('dashboard.winRateTrend')}: ${winRates
            .map((r) => `${(r * 100).toFixed(0)}%`)
            .join(', ')}`}
        >
          {/* CSS 折线图：线段 + 数据点 */}
          <View className="line-chart">
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
            {points.map((p, i) => (
              <View
                key={`pt-${i}`}
                className="data-point"
                style={{ left: `${p.left}%`, bottom: `${p.bottom}%` }}
              >
                <View className="point-dot" />
              </View>
            ))}
          </View>
          {/* X 轴标签 */}
          <View className="chart-labels">
            {data.labels.map((label, i) => (
              <Text key={`lb-${i}`} className="chart-label">
                {label}
              </Text>
            ))}
          </View>
        </View>
      )}
    </View>
  )
}
