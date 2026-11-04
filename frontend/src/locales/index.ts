/**
 * i18n 入口（总览 §3.7）
 * - 语言检测：本地存储 > 系统语言，默认 zh-CN
 * - 组件内使用 useTranslation（react-i18next）
 * - 组件外/常量文件使用 @/hooks/useI18n
 */
import Taro from '@tarojs/taro'
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import zhCN from './zh-CN'
import enUS from './en-US'

const LANGUAGE_KEY = 'app_language'

/** 检测初始语言：本地存储 > 系统语言，默认 zh-CN */
function detectLanguage(): string {
  try {
    const stored = Taro.getStorageSync(LANGUAGE_KEY)
    if (stored) return stored
  } catch {
    // 存储不可用时忽略
  }
  try {
    const sys = Taro.getSystemInfoSync()
    const lang = (sys.language || 'zh').toLowerCase()
    return lang.startsWith('en') ? 'en-US' : 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

/** 初始化 i18next（幂等，页面渲染前调用） */
export function initI18n() {
  if (i18n.isInitialized) return i18n
  i18n.use(initReactI18next).init({
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
    },
    lng: detectLanguage(),
    fallbackLng: 'zh-CN',
    interpolation: {
      escapeValue: false, // React 已转义
    },
  })
  return i18n
}

/** 切换语言并持久化 */
export function changeLanguage(lng: 'zh-CN' | 'en-US') {
  try {
    Taro.setStorageSync(LANGUAGE_KEY, lng)
  } catch {
    // 存储失败不阻塞切换
  }
  return i18n.changeLanguage(lng)
}

initI18n()

export { useTranslation } from 'react-i18next'
export default i18n
