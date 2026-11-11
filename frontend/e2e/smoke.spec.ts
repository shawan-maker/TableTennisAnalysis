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
  // R-FE-R1 批次A（FE-P1-9）：首页嵌入 PointsCard（训练积分/总积分/本月积分），
  // 子串匹配会命中多元素触发 strict mode violation——改 exact 锁定 TopBar 独立文本节点
  await expect(page.getByText('积分', { exact: true })).toBeVisible()
  // 概览卡（OverviewData.mock）
  await expect(page.getByText('胜率')).toBeVisible()
  await expect(page.getByText('快捷操作')).toBeVisible()
  await expect(page.getByText('打卡日历')).toBeVisible()
})
