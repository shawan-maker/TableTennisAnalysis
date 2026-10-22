# settings 模块 — 前端垂直切片设计

> **模块名称**：`settings`
> **前端目录**：`frontend/src/pages/settings/`
> **定位**：设置页，包含通知设置、隐私设置（引用 02-user 已有功能）、账号信息、关于
> **依据**：前端需求与界面设计 v2.0、API 详细设计 v1.3 §3（user 模块注销/导出）

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0（设置页：通知开关 + 隐私入口 + 账号信息 + 关于）
- [ ] 确认引用 02-user 模块已有功能：
  - 数据导出 → `useUserStore.requestExport()` + `pollExportStatus()`
  - 用户注销 → `useUserStore.requestDeletion()` + `fetchDeletionStatus()`
- [ ] 确认通知开关持久化方式：`Taro.setStorageSync` / `Taro.getStorageSync`
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：设置页 + 路由配置 + i18n
- [ ] 确认路由：`pages/settings/index`（非 TabBar 页，由个人主页 navigateTo 进入）

---

## 2. 页面组件（React + TSX + NutUI）

```tsx
// frontend/src/pages/settings/index.tsx
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Switch, Button, Toast, Popup, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useUserStore } from '@/stores/userStore'
import './index.scss'

/** 通知开关存储 Key 前缀 */
const NOTIF_STORAGE_PREFIX = 'notif_setting_'

/** 通知开关配置项 */
interface NotifSwitchItem {
  storageKey: string
  labelKey: string
  defaultOn: boolean
}

const NOTIF_ITEMS: NotifSwitchItem[] = [
  { storageKey: 'analysis_complete', labelKey: 'settings.notifAnalysisComplete', defaultOn: true },
  { storageKey: 'training_reminder', labelKey: 'settings.notifTrainingReminder', defaultOn: true },
  { storageKey: 'payment_success', labelKey: 'settings.notifPaymentSuccess', defaultOn: false },
]

/** 应用版本号 */
const APP_VERSION = '1.0.0'

export default function SettingsPage() {
  const { t } = useTranslation()
  const {
    // 数据导出
    exportTask, exportLoading, requestExport, pollExportStatus,
    // 用户注销
    deletionState, deletionLoading, requestDeletion, fetchDeletionStatus, cancelDeletion,
  } = useUserStore()

  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  // 通知开关状态
  const [notifStates, setNotifStates] = useState<Record<string, boolean>>({})

  // 注销确认弹窗
  const [deletionDialogVisible, setDeletionDialogVisible] = useState(false)
  const [deletionReason, setDeletionReason] = useState('')

  // 数据导出弹窗
  const [exportPopupVisible, setExportPopupVisible] = useState(false)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  // 初始化通知开关状态
  useEffect(() => {
    const states: Record<string, boolean> = {}
    NOTIF_ITEMS.forEach((item) => {
      const stored = Taro.getStorageSync(`${NOTIF_STORAGE_PREFIX}${item.storageKey}`)
      states[item.storageKey] = stored === '' ? item.defaultOn : stored === 'true'
    })
    setNotifStates(states)

    // 查询注销状态（如有冷静期内状态则显示）
    fetchDeletionStatus()
  }, [])

  /** 切换通知开关 */
  const handleNotifChange = (storageKey: string, val: boolean) => {
    setNotifStates((prev) => ({ ...prev, [storageKey]: val }))
    Taro.setStorageSync(`${NOTIF_STORAGE_PREFIX}${storageKey}`, String(val))
  }

  /** 跳转到数据导出 */
  const handleExport = async () => {
    setExportPopupVisible(true)
    try {
      await requestExport()
      const taskId = useUserStore.getState().exportTask?.task_id
      if (taskId) {
        await pollExportStatus(taskId)
      }
    } catch (err: any) {
      showToast(err?.message || t('user.exportFailed'))
    }
  }

  /** 下载导出文件 */
  const handleDownloadExport = () => {
    if (exportTask?.download_url) {
      Taro.downloadFile({
        url: exportTask.download_url,
        success: (res) => {
          Taro.openDocument({
            filePath: res.tempFilePath,
            fail: () => showToast(t('user.downloadFailed')),
          })
        },
        fail: () => showToast(t('user.downloadFailed')),
      })
    }
  }

  /** 确认注销 */
  const handleConfirmDeletion = async () => {
    try {
      await requestDeletion(deletionReason || t('user.deletionDefaultReason'))
      setDeletionDialogVisible(false)
      setDeletionReason('')
      showToast(t('user.deletionRequested'))
    } catch (err: any) {
      showToast(err?.message || t('user.deletionFailed'))
    }
  }

  /** 撤销注销 */
  const handleCancelDeletion = async () => {
    try {
      await cancelDeletion()
      showToast(t('user.deletionCancelled'))
    } catch (err: any) {
      showToast(err?.message || t('user.deletionCancelFailed'))
    }
  }

  /** 检查更新 */
  const handleCheckUpdate = () => {
    // 实际项目中调用 Taro.getUpdateManager() 或后端版本检查 API
    showToast(t('settings.alreadyLatest'))
  }

  /** 反馈意见 */
  const handleFeedback = () => {
    // 跳转到反馈页面或打开客服会话
    showToast(t('settings.feedbackComingSoon'))
  }

  return (
    <View className="settings-page">
      {/* ========== 1. 通知设置 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.notifSection')}</Text>
        <View className="settings-group">
          {NOTIF_ITEMS.map((item) => (
            <Cell
              key={item.storageKey}
              title={t(item.labelKey)}
              className="settings-cell"
            >
              <Switch
                checked={notifStates[item.storageKey] ?? item.defaultOn}
                onChange={(val) => handleNotifChange(item.storageKey, val)}
              />
            </Cell>
          ))}
        </View>
      </View>

      {/* ========== 2. 隐私设置 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.privacySection')}</Text>
        <View className="settings-group">
          {/* 数据导出入口 */}
          <Cell
            title={t('user.exportData')}
            subTitle={t('user.exportDataDesc')}
            isLink
            onClick={handleExport}
          />

          {/* 注销冷静期状态（如果存在） */}
          {deletionLoading && !deletionState ? (
            <Skeleton rows={2} loading={deletionLoading} />
          ) : deletionState?.status === 'cooling' ? (
            <View className="deletion-cooling-banner">
              <View className="banner-row">
                <Text className="banner-icon">⚠️</Text>
                <Text className="banner-text">{t('user.deletionCoolingTitle')}</Text>
              </View>
              <Button
                size="small"
                type="primary"
                loading={deletionLoading}
                onClick={handleCancelDeletion}
              >
                {t('user.cancelDeletion')}
              </Button>
            </View>
          ) : (
            <Cell
              title={t('user.deleteAccount')}
              subTitle={t('user.deleteAccountDesc')}
              isLink
              onClick={() => setDeletionDialogVisible(true)}
            />
          )}
        </View>
      </View>

      {/* ========== 3. 账号信息 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.accountSection')}</Text>
        <View className="settings-group">
          <Cell title={t('settings.appVersion')} value={`v${APP_VERSION}`} />
          <Cell
            title={t('settings.userAgreement')}
            isLink
            onClick={() => showToast(t('settings.openingDocument'))}
          />
          <Cell
            title={t('settings.privacyPolicy')}
            isLink
            onClick={() => showToast(t('settings.openingDocument'))}
          />
        </View>
      </View>

      {/* ========== 4. 关于 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.aboutSection')}</Text>
        <View className="settings-group">
          <Cell title={t('settings.appVersion')} value={`v${APP_VERSION}`} />
          <Cell
            title={t('settings.checkUpdate')}
            isLink
            onClick={handleCheckUpdate}
          />
          <Cell
            title={t('settings.feedback')}
            isLink
            onClick={handleFeedback}
          />
        </View>
      </View>

      {/* 注销确认弹窗 */}
      <Popup
        visible={deletionDialogVisible}
        position="bottom"
        round
        onClose={() => {
          setDeletionDialogVisible(false)
          setDeletionReason('')
        }}
      >
        <View className="deletion-popup">
          <View className="popup-header">
            <Text className="popup-title">{t('user.deletionDialogTitle')}</Text>
          </View>
          <View className="deletion-dialog-content">
            <Text className="deletion-warning">{t('user.deletionWarning')}</Text>
            <Text className="deletion-cooling-hint">
              {t('user.deletionCoolingHint')}
            </Text>
            <View className="deletion-reason-section">
              <Text className="reason-label">{t('user.deletionReasonLabel')}</Text>
              <Text className="reason-placeholder">{t('user.deletionReasonPlaceholder')}</Text>
            </View>
          </View>
          <View className="popup-actions">
            <Button
              type="primary"
              block
              loading={deletionLoading}
              onClick={handleConfirmDeletion}
            >
              {t('user.confirmDelete')}
            </Button>
            <Button
              block
              onClick={() => {
                setDeletionDialogVisible(false)
                setDeletionReason('')
              }}
            >
              {t('common.cancel')}
            </Button>
          </View>
        </View>
      </Popup>

      {/* 数据导出弹窗 */}
      <Popup
        visible={exportPopupVisible}
        position="bottom"
        round
        onClose={() => setExportPopupVisible(false)}
      >
        <View className="export-popup">
          <View className="popup-header">
            <Text className="popup-title">{t('user.exportTitle')}</Text>
          </View>
          <View className="export-dialog-content">
            <Text className="export-desc">{t('user.exportDesc')}</Text>
            {exportLoading && !exportTask && (
              <Skeleton rows={2} loading={exportLoading} />
            )}
            {exportTask && (
              <View className="export-status-row">
                <Text className="export-status-text">
                  {t(`user.exportStatus_${exportTask.status}`)}
                </Text>
                {exportTask.status === 'completed' && exportTask.download_url && (
                  <Text className="export-ready">{t('user.downloadExport')}</Text>
                )}
                {exportTask.status === 'failed' && (
                  <Text className="export-retry">{t('user.retryExport')}</Text>
                )}
              </View>
            )}
          </View>
          <View className="popup-actions">
            <Button
              type="primary"
              block
              onClick={() => {
                if (exportTask?.status === 'completed' && exportTask.download_url) {
                  handleDownloadExport()
                } else {
                  setExportPopupVisible(false)
                }
              }}
            >
              {exportTask?.status === 'completed' && exportTask.download_url
                ? t('user.downloadExport')
                : t('common.close')}
            </Button>
          </View>
        </View>
      </Popup>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

---

## 3. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/settings/index.scss

.settings-page {
  min-height: 100vh;
  background: var(--color-background);
  padding-bottom: var(--spacing-lg);
}

.settings-section {
  margin-top: var(--spacing-md);

  .section-title {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-secondary);
    margin: 0 var(--spacing-md) var(--spacing-sm);
  }

  .settings-group {
    background: var(--color-card);
    border-radius: var(--radius-md);
    overflow: hidden;
    margin: 0 var(--spacing-md);
    box-shadow: var(--shadow-card);

    .settings-cell {
      &:active {
        background: var(--color-press-overlay, rgba(0, 0, 0, 0.02));
      }
    }
  }
}

/* 注销冷静期横幅 */
.deletion-cooling-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
  border-bottom: 1px solid var(--color-divider);

  .banner-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    flex: 1;

    .banner-icon {
      font-size: 18px;
    }

    .banner-text {
      font-size: 13px;
      color: var(--color-primary);
      font-weight: 500;
    }
  }
}

/* 注销确认弹窗内容 */
.deletion-dialog-content {
  padding: var(--spacing-xs) 0;

  .deletion-warning {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-primary);
    margin-bottom: var(--spacing-sm);
  }

  .deletion-cooling-hint {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.5;
    margin-bottom: var(--spacing-md);
  }

  .deletion-reason-section {
    .reason-label {
      display: block;
      font-size: 13px;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-sm);
    }

    .reason-placeholder {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
  }
}

/* 数据导出弹窗内容 */
.export-dialog-content {
  padding: var(--spacing-xs) 0;

  .export-desc {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.5;
    margin-bottom: var(--spacing-sm-md);
  }

  .export-status {
    display: block;
    font-size: 13px;
    color: var(--color-text-primary);
  }

  .export-status-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);

    .export-status-text {
      font-size: 13px;
      color: var(--color-text-primary);
    }

    .export-ready {
      font-size: 13px;
      color: var(--color-success);
      font-weight: 600;
    }

    .export-retry {
      font-size: 13px;
      color: var(--color-primary);
    }
  }
}
```

---

## 4. 路由配置

```typescript
// frontend/src/app.config.ts（新增 settings 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/user/profile/index',
    'pages/settings/index',        // 新增：设置页
    // 注意：用户协议、隐私政策等子页面通过 H5 webview 承载
    // 路由格式：pages/settings/webview?url=xxx
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

> 设置页不是 TabBar 页面，由个人主页（`pages/user/profile/index`）通过 `Taro.navigateTo({ url: '/pages/settings/index' })` 进入。

---

## 5. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 settings 段）
{
  "settings": {
    "notifSection": "通知设置",
    "notifAnalysisComplete": "分析完成通知",
    "notifTrainingReminder": "训练提醒",
    "notifPaymentSuccess": "支付成功通知",
    "privacySection": "隐私设置",
    "accountSection": "账号信息",
    "aboutSection": "关于",
    "appVersion": "应用版本",
    "userAgreement": "用户协议",
    "privacyPolicy": "隐私政策",
    "checkUpdate": "检查更新",
    "feedback": "反馈意见",
    "alreadyLatest": "当前已是最新版本",
    "feedbackComingSoon": "反馈功能即将上线",
    "openingDocument": "正在打开文档..."
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 settings 段）
{
  "settings": {
    "notifSection": "Notifications",
    "notifAnalysisComplete": "Analysis Complete",
    "notifTrainingReminder": "Training Reminder",
    "notifPaymentSuccess": "Payment Success",
    "privacySection": "Privacy",
    "accountSection": "Account",
    "aboutSection": "About",
    "appVersion": "App Version",
    "userAgreement": "Terms of Service",
    "privacyPolicy": "Privacy Policy",
    "checkUpdate": "Check for Updates",
    "feedback": "Feedback",
    "alreadyLatest": "You are on the latest version",
    "feedbackComingSoon": "Feedback feature coming soon",
    "openingDocument": "Opening document..."
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/settings.ts

/** 通知开关存储 Key 前缀 */
export const NOTIF_STORAGE_PREFIX = 'notif_setting_'

/** 通知开关配置项 */
export interface NotifSwitchItem {
  storageKey: string
  labelKey: string
  defaultOn: boolean
}

export const NOTIF_ITEMS: NotifSwitchItem[] = [
  { storageKey: 'analysis_complete', labelKey: 'settings.notifAnalysisComplete', defaultOn: true },
  { storageKey: 'training_reminder', labelKey: 'settings.notifTrainingReminder', defaultOn: true },
  { storageKey: 'payment_success', labelKey: 'settings.notifPaymentSuccess', defaultOn: false },
]

/** 应用版本号 */
export const APP_VERSION = '1.0.0'
```

---

## 6. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** 通知开关状态必须持久化到 `Taro.setStorageSync`，**禁止** 仅依赖内存状态
- **ALL** 数据导出和用户注销功能**必须**复用 `02-user` 模块的 `useUserStore` 方法，**禁止** 重新实现
- **ALL** 注销冷静期内**必须**显示倒计时状态和撤销入口，**禁止** 隐藏冷静期
- **ALL** Switch 组件的 `checked` 状态必须与存储值同步
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在设置页内自行实现数据导出/注销的后端调用逻辑（通过 `useUserStore` 代理）
- **必须** 路由路径为 `pages/settings/index`（非 TabBar 页）
- **必须** TabBar 配置以总览 §3.4 `app.config.ts` 为准，此处不重复定义
