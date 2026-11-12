/**
 * 累计落点热图组件（06-data_dashboard/frontend.md §4.5）
 * 九宫格 grid + rgba 深浅（FS3 report 页同模式）+ 正手/反手/中路分布 + 来源报告数
 */
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { LandingHeatmapData } from '@/services/dashboard'
import { GRID_CELL_LABELS } from '@/constants/dashboard'
import './LandingHeatmap.scss'

interface Props {
  data: LandingHeatmapData | null
  loading: boolean
}

export default function LandingHeatmap({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading || !data) {
    return (
      <View className="landing-heatmap">
        <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
        <Skeleton rows={3} animated />
      </View>
    )
  }

  if (data.total_rallies === 0) {
    return (
      <View className="landing-heatmap">
        <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
        <View className="empty-state">
          <Text>{t('dashboard.noHeatmapData')}</Text>
        </View>
      </View>
    )
  }

  const grid = data.nine_grid
  const flatValues = grid.flat()
  const maxVal = Math.max(...flatValues)

  // 主色 #C92738 RGB（R-FE-R1 批次C FE-P3-10：FS8-7 深化后主色，JS 无法读 CSS 变量；
  // 修复前为调色前旧值 #E63946）
  const PRIMARY_RGB = '201, 39, 56'
  const getCellColor = (val: number) => {
    if (maxVal === 0) return `rgba(${PRIMARY_RGB}, 0)`
    const intensity = val / maxVal
    return `rgba(${PRIMARY_RGB}, ${0.15 + intensity * 0.85})`
  }

  return (
    <View className="landing-heatmap">
      <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
      <View className="heatmap-content">
        {/* 九宫格热图 */}
        <View
          className="nine-grid"
          role="img"
          aria-label={`${t('dashboard.landingHeatmap')}: ${t('dashboard.totalRallies')} ${data.total_rallies}`}
        >
          {grid.map((row, i) =>
            row.map((val, j) => {
              const idx = i * 3 + j
              return (
                <View className="grid-cell" key={`${i}-${j}`} style={{ background: getCellColor(val) }}>
                  <Text className="cell-value">{val}</Text>
                  <Text className="cell-label">{t(GRID_CELL_LABELS[idx])}</Text>
                </View>
              )
            })
          )}
        </View>

        {/* 分布图例（R-FE-R1 批次C FE-P3-8：三色圆点 dist-dot，设计 L799-809） */}
        <View className="distribution-row">
          <View className="dist-item">
            <View className="dist-dot" style={{ background: 'var(--color-primary)' }} />
            <Text>
              {t('dashboard.forehand')} {(data.distribution.forehand * 100).toFixed(0)}%
            </Text>
          </View>
          <View className="dist-item">
            <View className="dist-dot" style={{ background: 'var(--color-secondary)' }} />
            <Text>
              {t('dashboard.backhand')} {(data.distribution.backhand * 100).toFixed(0)}%
            </Text>
          </View>
          <View className="dist-item">
            <View className="dist-dot" style={{ background: 'var(--color-success)' }} />
            <Text>
              {t('dashboard.middle')} {(data.distribution.middle * 100).toFixed(0)}%
            </Text>
          </View>
        </View>

        {/* 来源（R-FE-R1 批次C FE-P3-9：两端对齐 stat-row 两行，替代单行拼接） */}
        <View className="heatmap-stats">
          <View className="stat-row">
            <Text className="stat-label">{t('dashboard.totalRallies')}</Text>
            <Text className="stat-value">{data.total_rallies}</Text>
          </View>
          <View className="stat-row">
            <Text className="stat-label">{t('dashboard.sourceReports')}</Text>
            <Text className="stat-value">{data.source_reports_count}</Text>
          </View>
        </View>
      </View>
    </View>
  )
}
