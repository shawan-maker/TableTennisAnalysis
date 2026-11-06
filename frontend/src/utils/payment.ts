/**
 * 支付展示工具（11-payment/frontend.md §4.1/§4.2 共用）
 * 货币符号走 i18n（payment.currencySymbol），金额分→元保留两位。
 */
import i18next from 'i18next'

/** 金额格式化（分 → 元） */
export function formatAmount(cents: number): string {
  return `${i18next.t('payment.currencySymbol')}${(cents / 100).toFixed(2)}`
}

/** 日期格式化（MM/DD HH:mm，本地时区） */
export function formatDate(isoStr: string): string {
  const d = new Date(isoStr)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}/${day} ${h}:${min}`
}
