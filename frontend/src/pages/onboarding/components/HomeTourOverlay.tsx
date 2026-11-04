/**
 * Step 2: 首页引导遮罩（14-tab-pages/onboarding.md §3.3）
 * 由首页（FS7 完整版）在 onboarding.showHomeTour=true 时渲染
 */
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './HomeTourOverlay.scss'

/** 首页引导遮罩点 */
const TOUR_SPOTS = [
  { key: 'overview', titleKey: 'onboarding.tourOverview', descKey: 'onboarding.tourOverviewDesc', position: 'top' },
  { key: 'quick', titleKey: 'onboarding.tourQuick', descKey: 'onboarding.tourQuickDesc', position: 'center' },
  { key: 'checkin', titleKey: 'onboarding.tourCheckin', descKey: 'onboarding.tourCheckinDesc', position: 'bottom' },
] as const

export default function HomeTourOverlay() {
  const { t } = useTranslation()
  const onboarding = useOnboardingStore()

  if (!onboarding.showHomeTour) return null

  const handleNext = () => {
    onboarding.setShowHomeTour(false)
    onboarding.nextStep()
  }

  return (
    <View className="home-tour-overlay" catchMove>
      {TOUR_SPOTS.map((spot) => (
        <View key={spot.key} className={`tour-spot tour-${spot.position}`}>
          <View className="tour-highlight" />
          <View className="tour-tooltip">
            <Text className="tour-title">{t(spot.titleKey)}</Text>
            <Text className="tour-desc">{t(spot.descKey)}</Text>
          </View>
        </View>
      ))}
      <View className="tour-actions">
        <Text className="tour-skip" onClick={() => onboarding.skip()}>
          {t('onboarding.skip')}
        </Text>
        <Text className="tour-next" onClick={handleNext}>
          {t('common.gotIt')}
        </Text>
      </View>
    </View>
  )
}
