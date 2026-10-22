# onboarding 模块 — 前端垂直切片设计

> **模块名称**：`onboarding`
> **前端目录**：`frontend/src/pages/onboarding/` + `frontend/src/stores/onboardingStore.ts`
> **定位**：新用户引导流程，检测新用户 → 5 步引导（填写档案 → 首页引导 → 录入比赛 → 上传视频 → 查看训练建议），进度持久化到 localStorage
> **依据**：前端需求与界面设计 v2.0 §P1.6 / F-6、API 详细设计 v1.3 §3.1

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P1.6（新用户引导流程，5 步引导）
- [ ] 阅读本模块涉及的 API 契约：
  - §3.1 GET /users/profile（判断是否新用户 + profile 完整度）
  - §3.2 PATCH /users/profile（Step 1 填写档案）
  - §5.2 POST /match-data（Step 3 录入第一场比赛）
  - §4.2 POST /video-analysis/upload（Step 4 上传第一个视频）
  - §7.x GET /training/advice（Step 5 查看训练建议）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：onboardingStore + 5 个引导步骤组件 + 路由配置 + i18n

---

## 2. 状态管理（Zustand Store）

引导进度持久化到 `localStorage`，避免用户中途退出后重复引导。

```typescript
// frontend/src/stores/onboardingStore.ts
import { create } from 'zustand'

/** 引导步骤 */
export type OnboardingStep =
  | 'profile'      // Step 1: 填写档案
  | 'home_tour'    // Step 2: 首页引导
  | 'first_match'  // Step 3: 录入第一场比赛
  | 'first_upload' // Step 4: 上传第一个视频
  | 'view_advice'  // Step 5: 查看训练建议
  | 'completed'    // 已完成

/** 引导步骤顺序 */
const STEP_ORDER: OnboardingStep[] = [
  'profile',
  'home_tour',
  'first_match',
  'first_upload',
  'view_advice',
  'completed',
]

const STORAGE_KEY = 'pingpong_onboarding'

interface OnboardingState {
  /** 是否为新用户（需要引导） */
  isNewUser: boolean
  /** 当前步骤 */
  currentStep: OnboardingStep
  /** 是否已完成引导 */
  completed: boolean
  /** 是否显示首页引导遮罩 */
  showHomeTour: boolean
  /** Steps 弹窗是否可见 */
  popupVisible: boolean

  /** 初始化：检查新用户状态 */
  initOnboarding: (createdAt: string, profileCompleteness: number) => void
  /** 从 localStorage 恢复进度 */
  loadFromStorage: () => void
  /** 保存进度到 localStorage */
  saveToStorage: () => void
  /** 进入下一步 */
  nextStep: () => void
  /** 跳到指定步骤 */
  goToStep: (step: OnboardingStep) => void
  /** 完成引导 */
  complete: () => void
  /** 跳过引导 */
  skip: () => void
  /** 打开/关闭 Steps 弹窗 */
  setPopupVisible: (visible: boolean) => void
  /** 显示/隐藏首页引导遮罩 */
  setShowHomeTour: (show: boolean) => void
}

function saveStorage(step: OnboardingStep, completed: boolean) {
  try {
    Taro.setStorageSync(STORAGE_KEY, JSON.stringify({ step, completed }))
  } catch {
    // localStorage 不可用时静默失败
  }
}

function loadStorage(): { step: OnboardingStep; completed: boolean } | null {
  try {
    const raw = Taro.getStorageSync(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // 读取失败静默处理
  }
  return null
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  isNewUser: false,
  currentStep: 'profile',
  completed: false,
  showHomeTour: false,
  popupVisible: false,

  initOnboarding: (createdAt: string, profileCompleteness: number) => {
    // 先从 localStorage 恢复
    const stored = loadStorage()
    if (stored?.completed) {
      set({ completed: true, isNewUser: false, currentStep: 'completed' })
      return
    }

    // 判断是否新用户：注册时间 < 24h 或 profile 完整度 < 30%
    const created = new Date(createdAt)
    const now = new Date()
    const hoursSinceCreated = (now.getTime() - created.getTime()) / (1000 * 60 * 60)
    const isNew = hoursSinceCreated < 24 || profileCompleteness < 30

    if (stored) {
      set({
        isNewUser: true,
        currentStep: stored.step,
        popupVisible: isNew,
      })
    } else {
      set({
        isNewUser: isNew,
        currentStep: isNew ? 'profile' : 'completed',
        completed: !isNew,
        popupVisible: isNew,
      })
    }
  },

  loadFromStorage: () => {
    const stored = loadStorage()
    if (stored) {
      set({
        currentStep: stored.step,
        completed: stored.completed,
        isNewUser: !stored.completed,
      })
    }
  },

  saveToStorage: () => {
    const { currentStep, completed } = get()
    saveStorage(currentStep, completed)
  },

  nextStep: () => {
    const { currentStep } = get()
    const idx = STEP_ORDER.indexOf(currentStep)
    const next = idx >= 0 && idx < STEP_ORDER.length - 1
      ? STEP_ORDER[idx + 1]
      : 'completed'
    set({ currentStep: next })
    get().saveToStorage()
    if (next === 'completed') {
      set({ completed: true, isNewUser: false, popupVisible: false })
    }
  },

  goToStep: (step: OnboardingStep) => {
    set({ currentStep: step })
    get().saveToStorage()
  },

  complete: () => {
    set({
      currentStep: 'completed',
      completed: true,
      isNewUser: false,
      popupVisible: false,
      showHomeTour: false,
    })
    get().saveToStorage()
  },

  skip: () => {
    set({
      currentStep: 'completed',
      completed: true,
      isNewUser: false,
      popupVisible: false,
      showHomeTour: false,
    })
    get().saveToStorage()
  },

  setPopupVisible: (visible: boolean) => set({ popupVisible: visible }),
  setShowHomeTour: (show: boolean) => set({ showHomeTour: show }),
}))
```

> **说明**：`Taro.setStorageSync` / `Taro.getStorageSync` 是 Taro 跨端存储 API，在 H5 端底层使用 localStorage，在小程序端使用各自存储。

---

## 3. 引导组件

### 3.1 引导主容器（Steps 弹窗）

```tsx
// frontend/src/pages/onboarding/index.tsx
import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Steps, Step, Button, Popup, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useAuthStore } from '@/stores/authStore'
import { useUserStore } from '@/stores/userStore'
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
    if (user?.created_at) {
      setProfileLoading(true)
      fetchProfile().then(() => {
        const userStore = useUserStore.getState()
        const completeness = userStore.profile?.profile.profile_completeness ?? 0
        onboarding.initOnboarding(user.created_at, completeness)
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
          <Skeleton rows={5} loading={profileLoading} />
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
```

### 3.2 Step 1: 填写档案（引导版）

```tsx
// frontend/src/pages/onboarding/StepProfile.tsx
import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import { Button, Toast, Input } from '@nutui/nutui-react'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './StepProfile.scss'

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
```

### 3.3 Step 2: 首页引导遮罩

```tsx
// frontend/src/pages/onboarding/HomeTourOverlay.tsx
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './HomeTourOverlay.scss'

/** 首页引导遮罩点 */
const TOUR_SPOTS = [
  { key: 'overview', titleKey: 'onboarding.tourOverview', descKey: 'onboarding.tourOverviewDesc', position: 'top' },
  { key: 'quick', titleKey: 'onboarding.tourQuick', descKey: 'onboarding.tourQuickDesc', position: 'center' },
  { key: 'checkin', titleKey: 'onboarding.tourCheckin', descKey: 'onboarding.tourCheckinDesc', position: 'bottom' },
] as const

export default function HomeTourOverlay() {
  const { t } = useTranslation()
  const onboarding = useOnboardingStore()

  if (!onboarding.showHomeTour) return null

  const handleNext = () => {
    onboarding.setShowHomeTour(false)
    onboarding.nextStep()
  }

  return (
    <View className="home-tour-overlay" catchMove>
      {TOUR_SPOTS.map((spot, idx) => (
        <View key={spot.key} className={`tour-spot tour-${spot.position}`}>
          <View className="tour-highlight" />
          <View className="tour-tooltip">
            <Text className="tour-title">{t(spot.titleKey)}</Text>
            <Text className="tour-desc">{t(spot.descKey)}</Text>
          </View>
        </View>
      ))}
      <View className="tour-actions">
        <Text className="tour-skip" onClick={() => onboarding.skip()}>
          {t('onboarding.skip')}
        </Text>
        <Text className="tour-next" onClick={handleNext}>
          {t('common.gotIt')}
        </Text>
      </View>
    </View>
  )
}
```

### 3.4 Step 3-5: 行为引导卡

```tsx
// frontend/src/pages/onboarding/ActionGuideCard.tsx
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useOnboardingStore } from '@/stores/onboardingStore'
import './ActionGuideCard.scss'

interface Props {
  step: 'first_match' | 'first_upload' | 'view_advice'
}

// 路由常量应引用 constants/routes.ts 统一管理
const ROUTE_MAP: Record<Props['step'], string> = {
  first_match: '/pages/match-data/quick-entry/index',
  first_upload: '/pages/video-analysis/upload/index',
  view_advice: '/pages/training/advice/index',
}

export default function ActionGuideCard({ step }: Props) {
  const { t } = useTranslation()
  const onboarding = useOnboardingStore()

  const handleStart = () => {
    onboarding.setPopupVisible(false)
    Taro.navigateTo({ url: ROUTE_MAP[step] })
  }

  const handleSkip = () => {
    onboarding.nextStep()
  }

  return (
    <View className="action-guide-card">
      <View className="guide-icon-row">
        <Text className="guide-icon">
          {step === 'first_match' ? '📝' : step === 'first_upload' ? '🎬' : '💡'}
        </Text>
      </View>
      <Text className="guide-title">{t(`onboarding.${step}_title`)}</Text>
      <Text className="guide-desc">{t(`onboarding.${step}_desc`)}</Text>
      <View className="guide-actions">
        <Button type="primary" block onClick={handleStart}>
          {t('onboarding.goNow')}
        </Button>
        <Text className="guide-skip" onClick={handleSkip}>
          {t('onboarding.doLater')}
        </Text>
      </View>
    </View>
  )
}
```

---

## 4. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/onboarding/index.scss

.onboarding-container {
  position: fixed;
  inset: 0;
  z-index: 1000;
  pointer-events: none;
}

.onboarding-popup {
  padding: var(--spacing-lg) var(--spacing-md);

  .popup-header {
    text-align: center;
    margin-bottom: var(--spacing-md);

    .popup-title {
      display: block;
      font-size: 24px;
      font-weight: bold;
      color: var(--color-primary);
    }

    .popup-subtitle {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }
  }

  .step-detail {
    background: var(--color-background);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    margin: var(--spacing-md) 0;

    .step-detail-title {
      display: block;
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-xs);
    }

    .step-detail-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
  }

  .popup-actions {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-sm);

    .skip-link {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }
}
```

```scss
// frontend/src/pages/onboarding/StepProfile.scss

.step-profile {
  padding: var(--spacing-md);
  background: var(--color-background);
  min-height: 100vh;
}

.form-section {
  margin-bottom: var(--spacing-md);

  .form-label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm);
  }

  .form-input {
    width: 100%;
    height: 44px;
    padding: 0 var(--spacing-md);
    background: var(--color-card);
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-md);
    font-size: 15px;
    color: var(--color-text-primary);
    box-sizing: border-box;
  }
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);

  .chip {
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--color-card);
    border: 2px solid transparent;
    border-radius: var(--radius-sm);
    font-size: 13px;
    color: var(--color-text-primary);

    &.active {
      background: color-mix(in srgb, var(--color-primary) 10%, transparent);
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
  }
}

.submit-btn {
  margin-top: var(--spacing-lg);
}
```

```scss
// frontend/src/pages/onboarding/HomeTourOverlay.scss

.home-tour-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6); /* 蒙层遮罩，非交互元素专用 */
  z-index: 1100;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: auto;
}

.tour-spot {
  position: absolute;
  display: flex;
  align-items: center;

  &.tour-top { top: 15%; left: 50%; transform: translateX(-50%); }
  &.tour-center { top: 45%; left: 50%; transform: translateX(-50%); }
  &.tour-bottom { top: 70%; left: 50%; transform: translateX(-50%); }

  .tour-highlight {
    width: 80vw;
    height: 60px;
    border: 2px solid var(--color-primary);
    border-radius: var(--radius-md);
    box-shadow: 0 0 0 2000px rgba(0, 0, 0, 0.6); /* 蒙层遮罩，非交互元素专用 */
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .tour-tooltip {
    position: relative;
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    width: 280px;
    margin-top: var(--spacing-2xl); /* P3-fix: 70px→48px (--spacing-2xl) */
    box-shadow: var(--shadow-card);

    .tour-title {
      display: block;
      font-size: 15px;
      font-weight: bold;
      color: var(--color-primary);
      margin-bottom: var(--spacing-xs);
    }

    .tour-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
  }
}

.tour-actions {
  position: absolute;
  bottom: var(--spacing-lg);
  right: var(--spacing-md);
  display: flex;
  gap: var(--spacing-md);

  .tour-skip {
    font-size: 13px;
    color: var(--color-text-inverse-secondary);
  padding: var(--spacing-sm);
  }

  .tour-next {
    font-size: 13px;
    color: var(--color-primary);
    font-weight: 600;
    padding: var(--spacing-sm);
  }
}
```

```scss
// frontend/src/pages/onboarding/ActionGuideCard.scss

.action-guide-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-lg);
  background: var(--color-card);
  border-radius: var(--radius-md);
  margin: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .guide-icon-row {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--color-primary) 10%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: var(--spacing-md);

    .guide-icon {
      font-size: 32px;
    }
  }

  .guide-title {
    font-size: 18px;
    font-weight: bold;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm);
    text-align: center;
  }

  .guide-desc {
    font-size: 13px;
    color: var(--color-text-secondary);
    text-align: center;
    line-height: 1.5;
    margin-bottom: var(--spacing-lg);
  }

  .guide-actions {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-sm);

    .guide-skip {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }
}
```

---

## 5. 路由配置

```typescript
// frontend/src/app.config.ts（新增 onboarding 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/onboarding/index',     // 新增：引导流程入口
    'pages/onboarding/profile/index',   // 新增：Step 1 档案填写
    // ... 其他页面
  ],
  // onboarding 不是 TabBar 页面，由首页 onShow 时检测触发
}
```

> 引导流程在用户登录后首次进入首页时检测触发。首页 `onShow` 生命周期中检查 `onboardingStore.isNewUser`，若为新用户则展示引导弹窗。

---

## 6. i18n

```json
// frontend/src/locales/zh-CN.json（新增 onboarding 段）
{
  "onboarding": {
    "welcome": "欢迎来到乒乓AI",
    "subtitle": "完成以下步骤，开启你的智能训练之旅",
    "stepProfile": "填写档案",
    "stepHomeTour": "首页引导",
    "stepFirstMatch": "录入比赛",
    "stepFirstUpload": "上传视频",
    "stepViewAdvice": "查看建议",
    "startStep": "开始此步骤",
    "skip": "跳过引导",
    "doLater": "稍后再做",
    "goNow": "立即前往",
    "nickname": "昵称",
    "nicknamePlaceholder": "请输入你的昵称",
    "nicknameRequired": "请输入昵称",
    "kqsRating": "开球网积分",
    "ratingPlaceholder": "500-3000（可选）",
    "profile_title": "完善你的个人档案",
    "profile_desc": "填写昵称、积分和打法，获取个性化训练建议",
    "home_tour_title": "了解首页功能",
    "home_tour_desc": "快速浏览首页各功能区位置与用途",
    "first_match_title": "录入第一场比赛",
    "first_match_desc": "记录你的比赛数据，开始积累数据资产",
    "first_upload_title": "上传第一个视频",
    "first_upload_desc": "上传比赛视频，体验 AI 智能分析",
    "view_advice_title": "查看训练建议",
    "view_advice_desc": "基于你的数据，获取个性化训练指导",
    "tourOverview": "数据概览",
    "tourOverviewDesc": "查看胜率、分析次数、连续打卡天数",
    "tourQuick": "快捷操作",
    "tourQuickDesc": "从这里快速进入 AI 分析、录入、记分等功能",
    "tourCheckin": "打卡日历",
    "tourCheckinDesc": "每天打卡记录训练，保持连续性"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 onboarding 段）
{
  "onboarding": {
    "welcome": "Welcome to PingPong AI",
    "subtitle": "Complete these steps to start your smart training journey",
    "stepProfile": "Profile",
    "stepHomeTour": "Home Tour",
    "stepFirstMatch": "First Match",
    "stepFirstUpload": "First Upload",
    "stepViewAdvice": "View Advice",
    "startStep": "Start this step",
    "skip": "Skip",
    "doLater": "Do later",
    "goNow": "Go now",
    "nickname": "Nickname",
    "nicknamePlaceholder": "Enter your nickname",
    "nicknameRequired": "Please enter a nickname",
    "kqsRating": "KQS Rating",
    "ratingPlaceholder": "500-3000 (optional)",
    "profile_title": "Complete your profile",
    "profile_desc": "Fill in your nickname, rating and playing style for personalized advice",
    "home_tour_title": "Explore the home page",
    "home_tour_desc": "Quick tour of the home page layout and features",
    "first_match_title": "Record your first match",
    "first_match_desc": "Enter match data to start building your data assets",
    "first_upload_title": "Upload your first video",
    "first_upload_desc": "Upload a match video for AI analysis",
    "view_advice_title": "View training advice",
    "view_advice_desc": "Get personalized training guidance based on your data",
    "tourOverview": "Overview",
    "tourOverviewDesc": "Check win rate, analysis count, and streak days",
    "tourQuick": "Quick Actions",
    "tourQuickDesc": "Access AI analysis, data entry, scoring and more",
    "tourCheckin": "Check-in Calendar",
    "tourCheckinDesc": "Check in daily to track your training consistency"
  }
}
```

---

## 7. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 新用户登录后首页弹出底部引导弹窗
- [ ] Steps 步骤条显示 5 步，当前步骤高亮
- [ ] 步骤说明文字显示当前步骤标题与描述
- [ ] 档案填写页表单布局：昵称 + 积分 + 打法 chips + 水平 chips
- [ ] 打法/水平 chip 选中时红色高亮
- [ ] 首页引导遮罩半透明黑色背景 + 高亮框
- [ ] 引导 tooltip 白色卡片 + 红色标题
- [ ] 行为引导卡片圆形图标 + 标题 + 描述 + 按钮
- [ ] 所有弹窗圆角 12px，8px 间距

### 功能验证
- [ ] 注册时间 < 24h 或 profile 完整度 < 30% 触发引导
- [ ] 引导进度持久化到 localStorage，中途退出后恢复
- [ ] Step 1 填写档案提交后更新 profile 并进入下一步
- [ ] Step 2 首页引导遮罩正确高亮功能区
- [ ] Step 3 点击"立即前往"跳转到比赛录入页
- [ ] Step 4 点击"立即前往"跳转到视频上传页
- [ ] Step 5 点击"立即前往"跳转到训练建议页
- [ ] 每步可"跳过"，跳过后标记完成
- [ ] 全部完成后不再弹出引导
- [ ] 老用户（注册 > 24h 且 profile 完整度 ≥ 30%）不触发引导

### i18n 验证
- [ ] 切换到英文后所有引导文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 8. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** 引导进度必须持久化到 localStorage，**禁止** 仅依赖内存状态
- **ALL** 新用户判断逻辑：注册时间 < 24h **或** profile 完整度 < 30%
- **ALL** localStorage 读写失败**不得**阻塞引导流程（catch 后静默处理）
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** Steps 弹窗使用 NutUI Steps + Popup 组件
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 引导流程中强制用户完成所有步骤（必须支持跳过）
- **禁止** 在引导中直接调用 `Taro.request`（通过 services 层）
- **必须** 引导完成后清空 `isNewUser` 标志，不再重复弹出
- **必须** 首页引导遮罩使用 `catchMove` 阻止底部滚动穿透
