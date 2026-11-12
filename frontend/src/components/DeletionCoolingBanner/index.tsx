/**
 * 注销冷静期横幅（公共组件，R-FE-R2 批次E FE-P3-33）
 * settings.md L620 反幻觉约束「冷静期必须显示倒计时」——修复前 profile 页有
 * 秒级倒计时而 settings 页仅图标+撤销按钮；本组件统一两页口径。
 * 消费方：user/profile + settings（deletionState 由 userStore 传入）。
 */
import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { AccountDeletionState } from '@/stores/userStore'
import './index.scss'

interface Props {
  deletionState: AccountDeletionState | null
  loading: boolean
  onCancel: () => void
}

export default function DeletionCoolingBanner({ deletionState, loading, onCancel }: Props) {
  const { t } = useTranslation()
  const [countdown, setCountdown] = useState('')

  // 秒级倒计时（cooling_ends_at 临近时切换「已执行」文案）
  useEffect(() => {
    if (deletionState?.status !== 'cooling' || !deletionState.cooling_ends_at) return
    const updateCountdown = () => {
      const endsAt = new Date(deletionState.cooling_ends_at!).getTime()
      const diff = endsAt - Date.now()
      if (diff <= 0) {
        setCountdown(t('user.deletionExecuted'))
        return
      }
      const hours = Math.floor(diff / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
      const seconds = Math.floor((diff % (1000 * 60)) / 1000)
      setCountdown(`${hours}h ${minutes}m ${seconds}s`)
    }
    updateCountdown()
    const timer = setInterval(updateCountdown, 1000)
    return () => clearInterval(timer)
  }, [deletionState, t])

  if (deletionState?.status !== 'cooling') return null

  return (
    <View className="deletion-cooling-banner">
      <View className="banner-row">
        <Text className="banner-icon" aria-hidden="true">⚠️</Text>
        <Text className="banner-title">{t('user.deletionCoolingTitle')}</Text>
      </View>
      <Text className="banner-desc">{t('user.deletionCoolingDesc')}</Text>
      <View className="countdown-row">
        <Text className="countdown-label">{t('user.deletionCountdown')}</Text>
        <Text className="countdown-value">{countdown}</Text>
      </View>
      <Button size="small" type="primary" loading={loading} onClick={onCancel}>
        {t('user.cancelDeletion')}
      </Button>
    </View>
  )
}
