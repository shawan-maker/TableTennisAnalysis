/**
 * 新用户引导主容器（14-tab-pages/onboarding.md §3.1）
 * Steps 弹窗：登录后首次进入首页时由首页 onShow 检测触发
 */
import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Steps, Step, Button, Popup, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/stores/authStore'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './index.scss'

/** 步骤定义 */
const STEP_DEFS = [
  { key: 'profile', titleKey: 'onboarding.stepProfile', icon: '👤' },
  { key: 'home_tour', titleKey: 'onboarding.stepHomeTour', icon: '🏠' },
  { key: 'first_match', titleKey: 'onboarding.stepFirstMatch', icon: '📝' },
  { key: 'first_upload', titleKey: 'onboarding.stepFirstUpload', icon: '🎬' },
  { key: 'view_advice', titleKey: 'onboarding.stepViewAdvice', icon: '💡' },
] as const

export default function OnboardingPage() {
  const { t } = useTranslation()
  const { user } = useAuthStore()
  const { fetchProfile } = useUserStore()
  const onboarding = useOnboardingStore()

  const [profileLoading, setProfileLoading] = useState(true)

  useEffect(() => {
    const createdAt = user?.created_at
    if (createdAt) {
      setProfileLoading(true)
      fetchProfile().then(() => {
        const userStore = useUserStore.getState()
        const completeness = userStore.profile?.profile.profile_completeness ?? 0
        onboarding.initOnboarding(createdAt, completeness)
        setProfileLoading(false)
      })
    } else {
      setProfileLoading(false)
    }
  }, [user?.created_at])

  if (profileLoading) {
    return (
      <View className="onboarding-container">
        <View className="onboarding-popup">
          <Skeleton rows={5} visible={profileLoading} />
        </View>
      </View>
    )
  }

  if (!onboarding.isNewUser || onboarding.completed) {
    return null
  }

  const currentIdx = STEP_DEFS.findIndex(
    (s) => s.key === onboarding.currentStep,
  )

  return (
    <View className="onboarding-container">
      {/* 引导完成弹窗 */}
      <Popup
        visible={onboarding.popupVisible}
        position="bottom"
        round
        onClose={() => onboarding.setPopupVisible(false)}
      >
        <View className="onboarding-popup">
          {/* 标题 */}
          <View className="popup-header">
            <Text className="popup-title">{t('onboarding.welcome')}</Text>
            <Text className="popup-subtitle">{t('onboarding.subtitle')}</Text>
          </View>

          {/* 步骤条 */}
          <Steps value={currentIdx}>
            {STEP_DEFS.map((step) => (
              <Step
                key={step.key}
                title={t(step.titleKey)}
                icon={step.icon}
              />
            ))}
          </Steps>

          {/* 当前步骤说明 */}
          <View className="step-detail">
            <Text className="step-detail-title">
              {t(`onboarding.${onboarding.currentStep}_title`)}
            </Text>
            <Text className="step-detail-desc">
              {t(`onboarding.${onboarding.currentStep}_desc`)}
            </Text>
          </View>

          {/* 操作按钮 */}
          <View className="popup-actions">
            <Button
              type="primary"
              block
              onClick={() => onboarding.nextStep()}
            >
              {t('onboarding.startStep')}
            </Button>
            <Text className="skip-link" onClick={() => onboarding.skip()}>
              {t('onboarding.skip')}
            </Text>
          </View>
        </View>
      </Popup>
    </View>
  )
}
