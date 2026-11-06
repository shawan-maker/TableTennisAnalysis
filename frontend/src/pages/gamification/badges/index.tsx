/**
 * 徽章列表页（09-gamification/frontend.md §4.3）
 * 已获得（彩色+日期）/ 未获得（灰度+进度条）两组；挂载徽章解锁弹层
 *
 * FS5-P3：设计样例 NutUI NavBar（返回）由默认导航栏承担（weapp
 * navigateTo 页自带返回箭头，config navigationBarTitleText 已设）。
 */
import { useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton, Empty } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useGamificationStore } from '@/stores/gamificationStore'
import BadgeUnlockPopup from '@/components/BadgeUnlockPopup'
import './index.scss'

export default function BadgesPage() {
  const { t } = useTranslation()
  const badges = useGamificationStore((s) => s.badges)
  const isLoadingBadges = useGamificationStore((s) => s.isLoadingBadges)
  const fetchBadges = useGamificationStore((s) => s.fetchBadges)

  useEffect(() => {
    fetchBadges()
  }, [fetchBadges])

  if (isLoadingBadges && !badges) {
    return (
      <View className="badges-page">
        <View className="badges-loading">
          <Skeleton rows={4} animated />
        </View>
      </View>
    )
  }

  const earned = badges?.earned ?? []
  const locked = badges?.locked ?? []
  const total = earned.length + locked.length

  return (
    <View className="badges-page">
      <ScrollView scrollY className="badges-scroll">
        {/* 已获得徽章 */}
        <View className="badges-section">
          <View className="section-header">
            <Text className="section-title">{t('gamification.earned')}</Text>
            <Text className="section-count">
              ({earned.length}/{total})
            </Text>
          </View>
          <View className="badges-grid">
            {earned.map((badge) => (
              <View key={badge.badge_id} className="badge-item earned">
                <Text className="badge-icon">{badge.icon}</Text>
                <Text className="badge-name">{badge.name}</Text>
                <Text className="badge-status">{t('gamification.earnedStatus')}</Text>
                {badge.earned_at && <Text className="badge-date">{badge.earned_at}</Text>}
              </View>
            ))}
            {earned.length === 0 && (
              <View className="empty-state">
                <Empty title={t('gamification.noBadgesYet')} />
              </View>
            )}
          </View>
        </View>

        {/* 未获得徽章 */}
        <View className="badges-section">
          <View className="section-header">
            <Text className="section-title">{t('gamification.locked')}</Text>
            <Text className="section-count">
              ({locked.length}/{total})
            </Text>
          </View>
          <View className="badges-grid">
            {locked.map((badge) => (
              <View key={badge.badge_id} className="badge-item locked">
                <Text className="badge-icon locked-icon">{badge.icon}</Text>
                <Text className="badge-name">{badge.name}</Text>
                <View className="badge-progress">
                  <View
                    className="progress-bar"
                    style={{
                      width: `${Math.min((badge.progress / badge.target) * 100, 100)}%`,
                    }}
                  />
                </View>
                <Text className="badge-progress-text">
                  {badge.progress}/{badge.target}
                </Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      {/* 徽章解锁弹层 */}
      <BadgeUnlockPopup />
    </View>
  )
}
