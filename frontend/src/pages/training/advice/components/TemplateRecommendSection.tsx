/**
 * 模板推荐组件（07-training_advice/frontend.md §4.5）
 * 推荐模板编码 + 查看详情按钮；无推荐时显示浏览模板列表入口
 */
import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import './TemplateRecommendSection.scss'

interface Props {
  templateCode: string | null
  onViewTemplate: () => void
}

export default function TemplateRecommendSection({ templateCode, onViewTemplate }: Props) {
  const { t } = useTranslation()

  return (
    <View className="template-recommend-section">
      <Text className="section-title">📋 {t('training.planTemplate')}</Text>
      <View className="recommend-card">
        {templateCode ? (
          <>
            <Text className="recommend-code">{templateCode}</Text>
            <Text className="recommend-desc">{t('training.recommendedTemplateDesc')}</Text>
            <Button type="primary" size="small" onClick={onViewTemplate}>
              {t('training.viewTemplateDetail')}
            </Button>
          </>
        ) : (
          <>
            <Text className="recommend-desc">{t('training.noRecommendedTemplate')}</Text>
            <Button plain type="primary" size="small" onClick={onViewTemplate}>
              {t('training.browseTemplates')}
            </Button>
          </>
        )}
      </View>
    </View>
  )
}
