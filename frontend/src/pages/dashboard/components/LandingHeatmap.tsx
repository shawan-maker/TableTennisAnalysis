/**
 * 累计落点热图组件（06-data_dashboard/frontend.md §4.5）
 * 九宫格 grid + rgba 深浅（FS3 report 页同模式）+ 正手/反手/中路分布 + 来源报告数
 */
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { LandingHeatmapData } from '@/services/dashboard'
import './LandingHeatmap.scss'

/** 九宫格标签（§7 GRID_CELL_LABELS 顺序） */
const GRID_CELL_LABELS = [
  'dashboard.cell.leftShort', 'dashboard.cell.midShort', 'dashboard.cell.rightShort',
  'dashboard.cell.leftMid', 'dashboard.cell.midMid', 'dashboard.cell.rightMid',
  'dashboard.cell.leftLong', 'dashboard.cell.midLong', 'dashboard.cell.rightLong',
]

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

  // 主色 #E63946 RGB（JS 无法读 CSS 变量）
  const PRIMARY_RGB = '230, 57, 70'
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

        {/* 分布图例 */}
        <View className="distribution-row">
          <Text className="distribution-item">
            {t('dashboard.forehand')} {(data.distribution.forehand * 100).toFixed(0)}%
          </Text>
          <Text className="distribution-item">
            {t('dashboard.backhand')} {(data.distribution.backhand * 100).toFixed(0)}%
          </Text>
          <Text className="distribution-item">
            {t('dashboard.middle')} {(data.distribution.middle * 100).toFixed(0)}%
          </Text>
        </View>

        {/* 来源 */}
        <View className="heatmap-footer">
          <Text className="footer-item">
            {t('dashboard.totalRallies')}: {data.total_rallies}
          </Text>
          <Text className="footer-item">
            {t('dashboard.sourceReports')}: {data.source_reports_count}
          </Text>
        </View>
      </View>
    </View>
  )
}
