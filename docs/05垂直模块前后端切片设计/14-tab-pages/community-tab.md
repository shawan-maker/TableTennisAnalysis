# community-tab 模块 — 前端垂直切片设计

> **模块名称**：`community-tab`
> **前端目录**：`frontend/src/pages/community/`
> **定位**：社区 Tab 占位页（Phase 2+ 功能预留），显示"即将上线"占位图与功能预告文案
> **依据**：前端需求与界面设计 v2.0 §P1.5 / F-5

> **设计决策 (CV-001/RT-007 修复)**：Phase 1 为 4-Tab 布局（首页/训练/赛事/我的），社区 Tab 在 Phase 1 不在 TabBar 中。界面设计 v2.0 的 5-Tab 为目标布局，Phase 2 社区上线后扩展为 5-Tab。Phase 1 社区入口通过"我的"页面二级菜单访问。

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P1.5（社区 Tab 占位页 — Phase 2+ 预留）
- [ ] 确认本切片范围：占位页 + 路由配置 + i18n
- [ ] 确认此页面**不调用任何 API**，纯静态占位
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）

---

## 2. 页面组件

```tsx
// frontend/src/pages/community/index.tsx
import { View, Text, Image } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import './index.scss'

/** 功能预告项 */
interface PreviewItem {
  icon: string
  titleKey: string
  descKey: string
}

const PREVIEW_ITEMS: PreviewItem[] = [
  {
    icon: '🏆',
    titleKey: 'community.previewRanking',
    descKey: 'community.previewRankingDesc',
  },
  {
    icon: '👥',
    titleKey: 'community.previewCircle',
    descKey: 'community.previewCircleDesc',
  },
  {
    icon: '🎯',
    titleKey: 'community.previewChallenge',
    descKey: 'community.previewChallengeDesc',
  },
  {
    icon: '📹',
    titleKey: 'community.previewShare',
    descKey: 'community.previewShareDesc',
  },
]

export default function CommunityTabPage() {
  const { t } = useTranslation()

  return (
    <View className="community-tab-page">
      {/* 占位图 */}
      <View className="placeholder-section">
        <Image
          className="placeholder-image"
          src="https://cdn.pingpongai.com/images/community-coming-soon.png"
          mode="aspectFit"
        />
        <Text className="coming-soon-title">{t('community.comingSoon')}</Text>
        <Text className="coming-soon-desc">{t('community.comingSoonDesc')}</Text>
      </View>

      {/* 功能预告 */}
      <View className="preview-section">
        <Text className="section-title">{t('community.previewTitle')}</Text>
        <View className="preview-grid">
          {PREVIEW_ITEMS.map((item, idx) => (
            <View className="preview-card" key={idx}>
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
```

---

## 3. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/community/index.scss

.community-tab-page {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
}

.placeholder-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-lg) 0;
  text-align: center;

  .placeholder-image {
    width: 200px;
    height: 200px;
    margin-bottom: var(--spacing-md);
  }

  .coming-soon-title {
    font-size: 24px;
    font-weight: bold;
    color: var(--color-primary);
    margin-bottom: var(--spacing-sm);
  }

  .coming-soon-desc {
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.5;
    max-width: 280px;
  }
}

.preview-section {
  margin-top: var(--spacing-lg);

  .section-title {
    display: block;
    font-size: 15px;
    font-weight: bold;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-md);
    text-align: center;
  }

  .preview-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-sm);
  }

  .preview-card {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    text-align: center;
    box-shadow: var(--shadow-card);
    opacity: 0.7;

    .preview-icon {
      font-size: 24px;
      display: block;
      margin-bottom: var(--spacing-xs);
    }

    .preview-name {
      display: block;
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-xs);
    }

    .preview-desc {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
  }
}

.footer-section {
  margin-top: auto;
  padding: var(--spacing-lg) 0;
  text-align: center;

  .footer-text {
    font-size: 12px;
    color: var(--color-text-secondary);
  }
}
```

---

## 4. 路由配置

```typescript
// frontend/src/app.config.ts（新增 community tab 占位页）
export default {
  pages: [
    'pages/home/index',
    'pages/community/index',   // 新增：社区 Tab 占位页
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

> Phase 1 阶段社区 Tab 不在 TabBar 中显示，仅保留路由。Phase 2+ 启用时取消注释 TabBar 配置。

---

## 5. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 community 段）
{
  "community": {
    "comingSoon": "即将上线",
    "comingSoonDesc": "社区功能正在紧锣密鼓地开发中，敬请期待",
    "previewTitle": "功能预告",
    "previewRanking": "积分排行",
    "previewRankingDesc": "查看球友积分排名，寻找实力相近的对手",
    "previewCircle": "球友圈",
    "previewCircleDesc": "分享训练心得，交流比赛经验",
    "previewChallenge": "挑战赛",
    "previewChallengeDesc": "参与线上挑战，赢取专属荣誉",
    "previewShare": "精彩分享",
    "previewShareDesc": "分享分析视频与精彩集锦",
    "footerHint": "关注公众号「乒乓AI」，第一时间获取上线通知"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 community 段）
{
  "community": {
    "comingSoon": "Coming Soon",
    "comingSoonDesc": "Community features are under development, stay tuned",
    "previewTitle": "Coming Features",
    "previewRanking": "Rankings",
    "previewRankingDesc": "View player rankings and find matched opponents",
    "previewCircle": "Player Circle",
    "previewCircleDesc": "Share training tips and match experiences",
    "previewChallenge": "Challenges",
    "previewChallengeDesc": "Join online challenges and earn badges",
    "previewShare": "Highlights",
    "previewShareDesc": "Share analysis videos and highlight reels",
    "footerHint": "Follow us for launch notifications"
  }
}
```

---

## 6. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** 占位页**禁止**调用任何 API
- **ALL** 功能预告卡片 opacity 0.7，表示未上线
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在 Phase 1 将社区 Tab 加入 TabBar（仅保留路由预留）
- **必须** 占位图使用 CDN 静态资源，不依赖业务后端
