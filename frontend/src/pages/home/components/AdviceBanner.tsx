/**
 * 训练提醒组件（00-home/frontend.md §4.7）
 * 橙色左边框横幅：概览响应 latest_advice_summary 摘要 + 未解决问题标签；
 * 点击跳训练建议页。
 */
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { AdviceSummary } from '@/services/home'
import './AdviceBanner.scss'

interface Props {
  advice: AdviceSummary | null
  loading: boolean
}

export default function AdviceBanner({ advice, loading }: Props) {
  const { t } = useTranslation()

  const handleClick = () => {
    if (advice) {
      Taro.navigateTo({ url: '/pages/training/advice/index' })
    }
  }

  if (loading) {
    return (
      <View className="advice-banner">
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        <View className="banner-placeholder">
          <Skeleton rows={2} animated />
        </View>
      </View>
    )
  }

  if (!advice) {
    return (
      <View className="advice-banner" onClick={handleClick}>
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        <Text className="banner-empty">{t('home.noAdviceYet')}</Text>
      </View>
    )
  }

  return (
    <View className="advice-banner" onClick={handleClick}>
      <View className="banner-header">
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        {advice.has_unresolved_issues && (
          <Text className="issue-tag">{t('home.hasIssues')}</Text>
        )}
      </View>
      <Text className="banner-summary">{advice.summary}</Text>
      {advice.latest_report_at && (
        <Text className="banner-time">
          {new Date(advice.latest_report_at).toLocaleDateString()}
        </Text>
      )}
    </View>
  )
}
