/**
 * FS8 Playwright 配置（04-前端实施计划.md FS8 / 02-测试计划.md §7）
 * E2E 运行于 Taro H5 构建产物（dist/，hash 路由），静态 server http-server。
 * API 一律经 page.route mock（E2E 验证前端行为编排，契约正确性由 30 套件单元/契约测试保障）。
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // E2E 串行（共享静态 server，避免资源争抢）
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    viewport: { width: 375, height: 667 }, // 设计 375 视口
  },
  webServer: {
    command: 'npx http-server dist -p 4173 --silent',
    url: 'http://localhost:4173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
