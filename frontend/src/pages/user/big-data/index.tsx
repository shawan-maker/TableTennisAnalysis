/**
 * 乒乓大数据页（02-user/frontend.md §4.3）
 * 趣味统计 + 间接胜利 + 最常用技术
 */
import { useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function BigDataPage() {
  const { t } = useTranslation()
  const { bigData, fetchBigData } = useUserStore()

  useEffect(() => {
    fetchBigData()
  }, [])

  if (!bigData) {
    return <View className="loading"><Skeleton rows={3} animated /></View>
  }

  return (
    <ScrollView scrollY className="big-data-page">
      {/* 趣味统计卡片 */}
      <View className="stat-grid">
        <View className="stat-card highlight">
          <Text className="stat-value">{bigData.highest_win_rating || '--'}</Text>
          <Text className="stat-label">{t('user.highestWinRating')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.win_streak}</Text>
          <Text className="stat-label">{t('user.winStreak')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.match_cities}</Text>
          <Text className="stat-label">{t('user.matchCities')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.total_opponents}</Text>
          <Text className="stat-label">{t('user.totalOpponents')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.total_matches}</Text>
          <Text className="stat-label">{t('user.totalMatches')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{(bigData.win_rate * 100).toFixed(0)}%</Text>
          <Text className="stat-label">{t('user.winRate')}</Text>
        </View>
      </View>

      {/* 间接胜利 */}
      {bigData.indirect_wins.length > 0 && (
        <View className="indirect-section">
          <View className="section-title">
            <Text className="title-icon">💡</Text>
            {t('user.indirectWins')}
          </View>
          <View className="indirect-chips">
            {bigData.indirect_wins.map((name, idx) => (
              <View key={idx} className="indirect-chip">
                <Text>{name}</Text>
              </View>
            ))}
          </View>
          <Text className="indirect-desc">{t('user.indirectWinsDesc')}</Text>
        </View>
      )}

      {/* 最常用技术 */}
      {bigData.favorite_shot && (
        <View className="favorite-shot-section">
          <View className="section-title">{t('user.favoriteShot')}</View>
          <View className="favorite-shot-card">
            <Text className="shot-icon">🏓</Text>
            <Text className="shot-name">
              {t(`technique.${bigData.favorite_shot}`)}
            </Text>
          </View>
        </View>
      )}
    </ScrollView>
  )
}
