/**
 * useI18n — 组件外/常量文件使用的 t() 获取 Hook（总览 §3.7 方式二）
 *
 * 组件内请优先使用 react-i18next 的 useTranslation；
 * 本 Hook 用于常量数组（labelKey 渲染时机）等场景。
 */
import i18n from '@/locales'

export function useI18n() {
  return (key: string, options?: Record<string, unknown>) =>
    i18n.t(key, options) as string
}

export default useI18n
