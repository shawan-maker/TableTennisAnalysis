/**
 * 社区 Tab 预告占位页（14-tab-pages/community-tab.md §2）
 * 完整功能 Phase 2+ 交付（04-前端实施计划.md §4.2 模块交付矩阵）；
 * TabBar 已含社区入口（app.config.ts 5-Tab），用户可达性成立。
 *
 * R-FE-R1 批次B（FE-P2-22/23）：替换 FS1 期 PagePlaceholder 通用占位
 * （全工程最后引用者，组件已删），按设计文档落地预告卡布局；
 * community 域 i18n 12 key 逐字取自 §5 明文（组件样例键名经脱敏，不复制）。
 */
import { View, Text, Image } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import './index.scss'

interface PreviewItem {
  icon: string
  titleKey: string
  descKey: string
}

/** 四功能预告卡（§5 键名顺序镜像 §2 样例 icon 顺序 🏆→👥→🎯→📹） */
const PREVIEW_ITEMS: PreviewItem[] = [
  { icon: '🏆', titleKey: 'community.previewRanking', descKey: 'community.previewRankingDesc' },
  { icon: '👥', titleKey: 'community.previewCircle', descKey: 'community.previewCircleDesc' },
  { icon: '🎯', titleKey: 'community.previewChallenge', descKey: 'community.previewChallengeDesc' },
  { icon: '📹', titleKey: 'community.previewShare', descKey: 'community.previewShareDesc' },
]

/** 占位图（cdn.pingpongai.com 为既有图床约定，真机验收时统一替换） */
const PLACEHOLDER_IMAGE = 'https://cdn.pingpongai.com/images/community-coming-soon.png'

export default function CommunityTab() {
  const { t } = useTranslation()

  return (
    <View className="community-tab-page">
      {/* 占位图区 */}
      <View className="placeholder-section">
        <Image
          className="placeholder-image"
          src={PLACEHOLDER_IMAGE}
          mode="aspectFit"
          alt={t('community.comingSoon')}
        />
        <Text className="coming-soon-title">{t('community.comingSoon')}</Text>
        <Text className="coming-soon-desc">{t('community.comingSoonDesc')}</Text>
      </View>

      {/* 功能预告 */}
      <View className="preview-section">
        <Text className="section-title">{t('community.previewTitle')}</Text>
        <View className="preview-grid">
          {PREVIEW_ITEMS.map((item) => (
            <View className="preview-card" key={item.titleKey}>
              <Text className="preview-icon">{item.icon}</Text>
              <Text className="preview-name">{t(item.titleKey)}</Text>
              <Text className="preview-desc">{t(item.descKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 底部提示 */}
      <View className="footer-section">
        <Text className="footer-text">{t('community.footerHint')}</Text>
      </View>
    </View>
  )
}
