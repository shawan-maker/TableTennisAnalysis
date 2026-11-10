/**
 * i18next 手动 mock（jest moduleNameMapper 映射）
 *
 * 根因：i18next 包 CJS 构建带 __esModule 无 default 导出 —— ts-jest CJS interop 下
 * `import i18next from 'i18next'` 解析为 undefined（生产 webpack 走 module 字段
 * ESM 构建不受影响）。store 层引用（如 trainingStore Toast 文案）经此 mock 提供
 * 可用的 t()，语义为「插值替换 + 原样返回 key」（真实翻译断言归 locales 测试与
 * 页面级测试）。
 */

type TOptions = { [k: string]: unknown } | undefined

function interpolate(template: string, opts: TOptions): string {
  if (!opts) return template
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (m, k) =>
    k in opts ? String((opts as Record<string, unknown>)[k]) : m
  )
}

const i18next = {
  isInitialized: true,
  language: 'zh-CN',
  t: jest.fn((key: string, opts?: TOptions) => interpolate(key, opts)),
  changeLanguage: jest.fn(() => Promise.resolve()),
  use: jest.fn(() => i18next),
  init: jest.fn(() => i18next),
}

export default i18next
export const { t, changeLanguage, use, init, isInitialized, language } = i18next
