/**
 * E2E 冒烟（FS8）：验证静态 server + hash 路由 + API mock + i18n 全链路可用。
 */
import { test, expect } from '@playwright/test'
import { setup, gotoPage, withAuth } from './helpers/auth'

test('首页在 mock 数据下正常渲染', async ({ page }) => {
  await setup(page, [], { open: '/pages/home/index' })
  await withAuth(page)
  // withAuth 的 addInitScript 需在 goto 前注入——setup 已 goto，改为直接重定向
  await page.goto('/#/pages/home/index')
  await page.waitForLoadState('networkidle')
  // TopBar 昵称 + KQS 积分（zh-CN 文本）
  await expect(page.getByText('E2E测试用户')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('积分')).toBeVisible()
  // 概览卡（OverviewData.mock）
  await expect(page.getByText('胜率')).toBeVisible()
  await expect(page.getByText('快捷操作')).toBeVisible()
  await expect(page.getByText('打卡日历')).toBeVisible()
})
