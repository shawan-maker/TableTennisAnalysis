/**
 * 徽章解锁弹层（09-gamification/frontend.md §8）
 * useBadgeUnlock 监听 WS badge_unlocked 事件 → Popup 底部弹层 + 刷新徽章列表
 * 页面挂载 <BadgeUnlockPopup />（checkin-calendar / badges / plans detail）
 *
 * FS5-P3：data 为徽章数组（后端 newly_unlocked），弹层逐枚展示；
 * 设计样例 NutUI 受控 Toast 改为 Popup position="bottom"（§8 样例注释口径）。
 */
import { View, Text } from '@tarojs/components'
import { Popup } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import useBadgeUnlock from '@/hooks/useBadgeUnlock'
import './BadgeUnlockPopup.scss'

export default function BadgeUnlockPopup() {
  const { t } = useTranslation()
  const { badgePopupVisible, unlockedBadges, handleBadgePopupClose } = useBadgeUnlock()

  return (
    <Popup
      visible={badgePopupVisible}
      position="bottom"
      round
      onClose={handleBadgePopupClose}
    >
      <View className="badge-unlock-popup">
        <Text className="badge-unlock-title">🎉 {t('gamification.badgeUnlocked')}</Text>
        <View className="badge-unlock-list">
          {unlockedBadges.map((badge) => (
            <View className="badge-unlock-item" key={badge.badge_id}>
              <Text className="badge-unlock-icon">{badge.icon}</Text>
              <Text className="badge-unlock-name">{badge.name}</Text>
            </View>
          ))}
        </View>
        <Text className="badge-unlock-hint">{t('gamification.badgeUnlockHint')}</Text>
      </View>
    </Popup>
  )
}
