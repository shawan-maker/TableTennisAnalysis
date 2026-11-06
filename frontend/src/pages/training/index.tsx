/**
 * 训练 Tab 入口页（14-tab-pages/training-tab.md §4）
 * 纯导航聚合页：AI 视频分析 / 数据看板 / 比赛数据录入 / 训练建议 4 入口
 * 禁止 API 调用与数据处理逻辑（反幻觉约束 §9）
 */
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import './index.scss'

/** 训练入口项定义 */
interface TrainingEntry {
  icon: string
  titleKey: string
  descKey: string
  route: string
  color: string
  /** 图标底色（对应入口色 8% 透明度；CSS 变量无法拼接 hex 后缀，用 color-mix） */
  bg: string
}

/** 4 个训练入口（路由常量内联于 TRAINING_ENTRIES，§7 TRAINING_ROUTES 同构） */
const TRAINING_ENTRIES: TrainingEntry[] = [
  {
    icon: '🤖',
    titleKey: 'trainingTab.aiAnalysis',
    descKey: 'trainingTab.aiAnalysisDesc',
    route: '/pages/video-analysis/upload/index',
    color: 'var(--color-primary)',
    bg: 'color-mix(in srgb, var(--color-primary) 8%, transparent)',
  },
  {
    icon: '📊',
    titleKey: 'trainingTab.dataBoard',
    descKey: 'trainingTab.dataBoardDesc',
    route: '/pages/dashboard/index',
    color: 'var(--color-secondary)',
    bg: 'color-mix(in srgb, var(--color-secondary) 8%, transparent)',
  },
  {
    icon: '📝',
    titleKey: 'trainingTab.matchEntry',
    descKey: 'trainingTab.matchEntryDesc',
    route: '/pages/match-data/quick-entry/index',
    color: 'var(--color-accent)',
    bg: 'color-mix(in srgb, var(--color-accent) 8%, transparent)',
  },
  {
    icon: '💡',
    titleKey: 'trainingTab.advice',
    descKey: 'trainingTab.adviceDesc',
    route: '/pages/training/advice/index',
    color: 'var(--color-success)',
    bg: 'color-mix(in srgb, var(--color-success) 8%, transparent)',
  },
]

export default function TrainingTabPage() {
  const { t } = useTranslation()

  const handleNavigate = (entry: TrainingEntry) => {
    Taro.navigateTo({ url: entry.route })
  }

  return (
    <View className="training-tab-page">
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">{t('trainingTab.title')}</Text>
        <Text className="page-subtitle">{t('trainingTab.subtitle')}</Text>
      </View>

      {/* 入口列表 */}
      <View className="entry-list">
        {TRAINING_ENTRIES.map((entry) => (
          <View
            className="entry-card"
            key={entry.route}
            onClick={() => handleNavigate(entry)}
          >
            <View
              className="entry-icon-wrapper"
              style={{ background: entry.bg }}
            >
              <Text className="entry-icon" style={{ color: entry.color }}>
                {entry.icon}
              </Text>
            </View>
            <View className="entry-content">
              <Text className="entry-title">{t(entry.titleKey)}</Text>
              <Text className="entry-desc">{t(entry.descKey)}</Text>
            </View>
            <Text className="entry-arrow">›</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
