/**
 * E2E 登录/导航 helper（FS8）
 * - loginByPhone：走真实登录页 UI（手机号 + 验证码 → phone-login）
 * - gotoPage：hash 路由直达（Taro H5 router 默认 hash 模式）
 * - 语言固定 zh-CN（localStorage app_language 优先于系统语言，headless 默认 en）
 */
import type { Page } from '@playwright/test'
import { installApiMocks, type MockRoute } from './mock-api'
import { baseMocks } from './base-mocks'

/**
 * 固定语言 zh-CN（detectLanguage 存储优先；headless chromium 系统语言默认 en-US）
 * + 安装 mocks（extraMocks 优先级高于 baseMocks）+ 可选预置登录态 + 打开页面。
 */
export async function setup(
  page: Page,
  extraMocks: MockRoute[] = [],
  opts: {
    requiresConsent?: boolean
    open?: string
    auth?: boolean
  } = {},
) {
  const routes = [...extraMocks, ...baseMocks({ requiresConsent: opts.requiresConsent ?? false })]
  await installApiMocks(page, routes)
  const auth = opts.auth ?? false
  await page.addInitScript(
    (a) => {
      localStorage.setItem('app_language', 'zh-CN')
      if (a) {
        // Taro H5 storage 格式：setStorageSync 存 JSON.stringify({data})，
        // getStorageSync 须解析出 {data} 才返回（裸字符串解析失败 → 恒空 →
        // authStore.accessToken 为空、useWebSocket 无 Token 不连接）
        localStorage.setItem('access_token', JSON.stringify({ data: 'e2e-access-token' }))
        localStorage.setItem('refresh_token', JSON.stringify({ data: 'e2e-refresh-token' }))
      }
    },
    auth
  )
  const open = opts.open ?? '/pages/auth/login/index'
  await page.goto(`/#${open}`)
  await page.waitForLoadState('networkidle')
  return routes
}

/** 登录页真实 UI 操作：手机号 + 验证码 + 点登录（exact：排除「微信一键登录」）
 * Taro H5 的 Input 渲染双层（taro-input-core + 原生 weui-input），须选原生 input */
export async function loginByPhone(page: Page, phone = '13800138000', code = '123456') {
  await page.locator('input[placeholder="请输入手机号"]').fill(phone)
  await page.locator('input[placeholder="请输入验证码"]').fill(code)
  await page.getByRole('button', { name: '登录', exact: true }).click()
}

/** hash 路由直达某页 */
export async function gotoPage(page: Page, path: string) {
  await page.goto(`/#${path}`)
  await page.waitForLoadState('networkidle')
}

/** 预置已登录态（免 UI，用于非登录主线的路径；Taro H5 storage 格式同 setup） */
export async function withAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', JSON.stringify({ data: 'e2e-access-token' }))
    localStorage.setItem('refresh_token', JSON.stringify({ data: 'e2e-refresh-token' }))
  })
}
