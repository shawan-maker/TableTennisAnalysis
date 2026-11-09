/**
 * 新用户引导主容器（14-tab-pages/onboarding.md §3.1）
 * Steps 弹窗：登录后首次进入首页时由首页 onShow 检测触发（FS7 串接）
 *
 * 分步分发（FS7）：
 * - profile：Steps 弹窗 →「开始此步骤」navigateTo 档案填写页（提交后
 *   nextStep + switchTab 首页，见 onboarding/profile/index.tsx）
 * - home_tour：Steps 弹窗 →「开始此步骤」navigateBack 回首页 + 开启
 *   HomeTourOverlay 遮罩（遮罩「知道了」nextStep）
 * - first_match / first_upload / view_advice：弹窗内渲染 ActionGuideCard
 *   （§3.4 行为引导卡，goNow 跳目标页 / doLater nextStep）
 */
import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Steps, Step, Button, Popup, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/stores/authStore'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import ActionGuideCard from './components/ActionGuideCard'
import './index.scss'

/** 步骤定义 */
const STEP_DEFS = [
  { key: 'profile', titleKey: 'onboarding.stepProfile', icon: '👤' },
  { key: 'home_tour', titleKey: 'onboarding.stepHomeTour', icon: '🏠' },
  { key: 'first_match', titleKey: 'onboarding.stepFirstMatch', icon: '📝' },
  { key: 'first_upload', titleKey: 'onboarding.stepFirstUpload', icon: '🎬' },
  { key: 'view_advice', titleKey: 'onboarding.stepViewAdvice', icon: '💡' },
] as const

/** 行为引导步骤（ActionGuideCard 承载） */
const ACTION_STEPS = ['first_match', 'first_upload', 'view_advice'] as const

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
  const isActionStep = (ACTION_STEPS as readonly string[]).includes(onboarding.currentStep)

  /** 「开始此步骤」分步分发（FS7 串接） */
  const handleStart = () => {
    if (onboarding.currentStep === 'profile') {
      onboarding.setPopupVisible(false)
      Taro.navigateTo({ url: '/pages/onboarding/profile/index' })
    } else if (onboarding.currentStep === 'home_tour') {
      // 关弹窗回首页，开启首页功能遮罩（HomeTourOverlay 由首页渲染）
      onboarding.setPopupVisible(false)
      onboarding.setShowHomeTour(true)
      Taro.navigateBack()
    }
  }

  return (
    <View className="onboarding-container">
      {/* 引导弹窗 */}
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

          {isActionStep ? (
            /* Step 3-5: 行为引导卡（§3.4：goNow 跳目标页 / doLater nextStep） */
            <ActionGuideCard
              step={onboarding.currentStep as (typeof ACTION_STEPS)[number]}
            />
          ) : (
            <>
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
                  onClick={handleStart}
                >
                  {t('onboarding.startStep')}
                </Button>
                <Text className="skip-link" onClick={() => onboarding.skip()}>
                  {t('onboarding.skip')}
                </Text>
              </View>
            </>
          )}
        </View>
      </Popup>
    </View>
  )
}
