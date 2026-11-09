/**
 * 快捷操作宫格组件（00-home/frontend.md §4.4）
 * 2×2 四入口：AI 分析 / 手动录入 / 记分牌 / 数据看板。
 * 路由走 constants/home.ts QUICK_ROUTES（反幻觉约束：独立路由常量）。
 */
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import { QUICK_ROUTES } from '@/constants/home'
import './QuickGrid.scss'

interface QuickItem {
  icon: string
  titleKey: string
  descKey: string
  route: string
}

const ITEMS: QuickItem[] = [
  { icon: '🤖', titleKey: 'home.aiAnalysis', descKey: 'home.aiAnalysisDesc', route: QUICK_ROUTES.aiAnalysis },
  { icon: '📝', titleKey: 'home.manualEntry', descKey: 'home.manualEntryDesc', route: QUICK_ROUTES.manualEntry },
  { icon: '🏓', titleKey: 'home.scoreboard', descKey: 'home.scoreboardDesc', route: QUICK_ROUTES.scoreboard },
  { icon: '📊', titleKey: 'home.dataBoard', descKey: 'home.dataBoardDesc', route: QUICK_ROUTES.dataBoard },
]

export default function QuickGrid() {
  const { t } = useTranslation()

  const handleNavigate = (item: QuickItem) => {
    Taro.navigateTo({ url: item.route })
  }

  return (
    <View className="quick-grid">
      <Text className="section-title">{t('home.quickActions')}</Text>
      <View className="grid-container">
        {ITEMS.map((item) => (
          <View
            className="grid-item"
            key={item.route}
            onClick={() => handleNavigate(item)}
          >
            <Text className="item-icon">{item.icon}</Text>
            <Text className="item-title">{t(item.titleKey)}</Text>
            <Text className="item-desc">{t(item.descKey)}</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
