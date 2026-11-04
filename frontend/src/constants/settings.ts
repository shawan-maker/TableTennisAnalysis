/**
 * settings 常量（14-tab-pages/settings.md §5）
 */

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
