/**
 * Step 3-5: 行为引导卡（14-tab-pages/onboarding.md §3.4）
 */
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './ActionGuideCard.scss'

interface Props {
  step: 'first_match' | 'first_upload' | 'view_advice'
}

// 路由常量应引用 constants/routes.ts 统一管理
const ROUTE_MAP: Record<Props['step'], string> = {
  first_match: '/pages/match-data/quick-entry/index',
  first_upload: '/pages/video-analysis/upload/index',
  view_advice: '/pages/training/advice/index',
}

export default function ActionGuideCard({ step }: Props) {
  const { t } = useTranslation()
  const onboarding = useOnboardingStore()

  const handleStart = () => {
    onboarding.setPopupVisible(false)
    Taro.navigateTo({ url: ROUTE_MAP[step] })
  }

  const handleSkip = () => {
    onboarding.nextStep()
  }

  return (
    <View className="action-guide-card">
      <View className="guide-icon-row">
        <Text className="guide-icon">
          {step === 'first_match' ? '📝' : step === 'first_upload' ? '🎬' : '💡'}
        </Text>
      </View>
      <Text className="guide-title">{t(`onboarding.${step}_title`)}</Text>
      <Text className="guide-desc">{t(`onboarding.${step}_desc`)}</Text>
      <View className="guide-actions">
        <Button type="primary" block onClick={handleStart}>
          {t('onboarding.goNow')}
        </Button>
        <Text className="guide-skip" onClick={handleSkip}>
          {t('onboarding.doLater')}
        </Text>
      </View>
    </View>
  )
}
