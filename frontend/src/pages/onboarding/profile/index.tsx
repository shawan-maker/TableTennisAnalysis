/**
 * Step 1: 填写档案（引导版）（14-tab-pages/onboarding.md §3.2）
 */
import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Button, Toast, Input } from '@nutui/nutui-react'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './index.scss'

const PLAYING_STYLES = [
  { value: 'loop', labelKey: 'user.style_loop' },
  { value: 'quick_attack', labelKey: 'user.style_quick_attack' },
  { value: 'chop', labelKey: 'user.style_chop' },
  { value: 'allround', labelKey: 'user.style_allround' },
]

const SELF_LEVELS = [
  { value: 'beginner', labelKey: 'user.level_beginner' },
  { value: 'intermediate', labelKey: 'user.level_intermediate' },
  { value: 'advanced', labelKey: 'user.level_advanced' },
]

export default function StepProfile() {
  const { t } = useTranslation()
  const { updateProfile } = useUserStore()
  const onboarding = useOnboardingStore()
  const [nickname, setNickname] = useState('')
  const [rating, setRating] = useState('')
  const [playingStyle, setPlayingStyle] = useState('')
  const [selfLevel, setSelfLevel] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const handleSubmit = async () => {
    if (!nickname.trim()) {
      setToastMsg(t('onboarding.nicknameRequired'))
      setToastVisible(true)
      return
    }
    setSubmitting(true)
    try {
      await updateProfile({
        playing_style: playingStyle || undefined,
        self_assessed_level: selfLevel || undefined,
      })
      onboarding.nextStep()
      Taro.switchTab({ url: '/pages/home/index' })
    } catch (err: any) {
      setToastMsg(err?.message || t('common.saveFailed'))
      setToastVisible(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View className="step-profile">
      <View className="form-section">
        <Text className="form-label">{t('onboarding.nickname')}</Text>
        <Input
          className="form-input"
          placeholder={t('onboarding.nicknamePlaceholder')}
          value={nickname}
          onChange={(val) => setNickname(val)}
        />
      </View>

      <View className="form-section">
        <Text className="form-label">{t('onboarding.kqsRating')}</Text>
        <Input
          className="form-input"
          type="number"
          placeholder={t('onboarding.ratingPlaceholder')}
          value={rating}
          onChange={(val) => setRating(val)}
        />
      </View>

      <View className="form-section">
        <Text className="form-label">{t('user.playingStyle')}</Text>
        <View className="chip-row">
          {PLAYING_STYLES.map((s) => (
            <View
              key={s.value}
              className={`chip ${playingStyle === s.value ? 'active' : ''}`}
              onClick={() => setPlayingStyle(s.value)}
            >
              <Text>{t(s.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className="form-section">
        <Text className="form-label">{t('user.selfLevel')}</Text>
        <View className="chip-row">
          {SELF_LEVELS.map((l) => (
            <View
              key={l.value}
              className={`chip ${selfLevel === l.value ? 'active' : ''}`}
              onClick={() => setSelfLevel(l.value)}
            >
              <Text>{t(l.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      <Button
        type="primary"
        block
        loading={submitting}
        onClick={handleSubmit}
        className="submit-btn"
      >
        {t('common.continue')}
      </Button>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
