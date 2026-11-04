/**
 * 占位页统一组件
 * FS1 交付 Tab 骨架与 34 功能页中的 13 页完整实现，
 * 其余 26 页 + 3 Tab 骨架以此组件占位，后续 Sprint 按模块交付矩阵替换。
 */
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import './index.scss'

interface Props {
  /** 模块标识（如 video-analysis，路由路径性质非用户文案） */
  module: string
  /** 交付 Sprint（如 FS3） */
  sprint: string
}

export default function PagePlaceholder({ module, sprint }: Props) {
  const { t } = useTranslation()
  return (
    <View className="page-placeholder">
      <Text className="placeholder-icon">🏓</Text>
      <Text className="placeholder-title">{t('app.name')}</Text>
      <Text className="placeholder-text">{t('common.pageInDevelopment')}</Text>
      <Text className="placeholder-meta">{module} · {sprint}</Text>
    </View>
  )
}
