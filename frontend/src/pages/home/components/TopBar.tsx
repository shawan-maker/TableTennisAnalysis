/**
 * 顶部栏组件（00-home/frontend.md §4.2）
 * 深蓝背景：头像 + 昵称 + KQS 积分 + 通知铃铛（NotificationBell，FS6 组件迁回首页）。
 *
 * FS7-P3：
 * - 积分数据源 userStore.profile.profile.kqs_rating（authStore.user 无 profile 嵌套）；
 * - 铃铛复用 components/NotificationBell（useWebSocket 单例 + tabBar 角标，
 *   12-notification §5「显示在首页顶部」设计意图落地）；
 * - 头像点击 switchTab 到「我的」（设计 §4.2 handleAvatar 同构）。
 */
import { useEffect } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import NotificationBell from '@/components/NotificationBell'
import { useUserStore } from '@/stores/userStore'
import { DEFAULT_AVATAR } from '@/constants/home'
import './TopBar.scss'

export default function TopBar() {
  const { t } = useTranslation()
  const { profile, fetchProfile } = useUserStore()

  useEffect(() => {
    fetchProfile().catch(() => {})
  }, [fetchProfile])

  const nickname = profile?.nickname || ''
  const rating = profile?.profile.kqs_rating ?? null

  const handleAvatar = () => {
    Taro.switchTab({ url: '/pages/user/profile/index' })
  }

  return (
    <View className="home-topbar">
      <View className="topbar-user" onClick={handleAvatar}>
        <Image
          className="user-avatar"
          src={profile?.avatar_url || DEFAULT_AVATAR}
          mode="aspectFill"
        />
        <View className="user-info">
          <Text className="user-nickname">{nickname || t('home.guest')}</Text>
          <View className="user-rating-row">
            <Text className="rating-label">{t('home.rating')}</Text>
            <Text className="rating-value">{rating ?? '--'}</Text>
          </View>
        </View>
      </View>

      <View className="topbar-bell">
        <NotificationBell />
      </View>
    </View>
  )
}
