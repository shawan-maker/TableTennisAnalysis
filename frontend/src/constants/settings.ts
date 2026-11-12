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

/**
 * 协议页 WebView URL（R-FE-R1 批次B FE-P2-21：settings.md L524-525
 * 「用户协议、隐私政策子页面通过 H5 webview 承载：pages/settings/webview?url=xxx」）
 * 生产域名为部署期配置项（须配入小程序业务域名白名单），当前占位官方页面
 */
export const URL_USER_AGREEMENT = 'https://example.com/terms'
export const URL_PRIVACY_POLICY = 'https://example.com/privacy'
