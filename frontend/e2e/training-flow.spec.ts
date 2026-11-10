/**
 * E2E-04 训练闭环全流程（docs/07实施计划/02-测试计划.md §7.4）
 * 分析 → 训练建议 → 训练模板（会员守卫）→ 方案 → 训练单完成（+5 分）→ 重新评估。
 *
 * 关键实现口径：
 * - 步骤 1-3（两次分析 + progress_snapshot 生成）为后端域（627 用例覆盖），
 *   前端入口取 contextual advice（baseMocks TRAINING_ADVICE，report_id=7 链路）
 * - 步骤 5「查看训练模板 会员权限」：免费态 HTTP 403 + code 40300 →
 *   isMembershipError → Empty 升级引导分支（FS8-5 验收点）→ 跳会员中心；
 *   state.member 测试侧翻转模拟开通后重进（付费链路归 E2E-03）
 * - 步骤 7「标记训练单完成 积分 +5」：completeTrainingSession Toast
 *   （training.sessionCompleted i18n，FS8-5 修复：此前 store 硬编码英文）+
 *   进度联动 1/2 → 2/2；积分入账/打卡级联为后端域
 * - 步骤 8-9「重新评估 + 方案调整历史」：Toast 文案取后端 envelope message；
 *   调整历史经 store fetchPlanAdjustments 刷新（waitForRequest 断言）
 * - badge_unlocked WS 弹层（plans detail 页挂 BadgeUnlockPopup）：完成训练单
 *   触发徽章解锁 → Popup 展示 + fetchBadges 徽章列表刷新
 */
import { test, expect } from '@playwright/test'
import { setup, gotoPage } from './helpers/auth'
import { installWsMock, pushWsMessage } from './helpers/ws-mock'
import { createTrainingMocks, PLAN_ID } from './helpers/training-mocks'

test('E2E-04 训练闭环：建议→模板守卫升级引导→方案→训练单完成+5分→重新评估→徽章弹层', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const { routes, state } = createTrainingMocks()

  // WS mock：plans detail 页 BadgeUnlockPopup 消费 badge_unlocked 推送
  await installWsMock(page)

  // ── 训练建议（contextual，§7.4 步骤 4：基于历史对比）──
  await setup(page, routes, { auth: true, open: '/pages/training/advice/index' })
  await expect(page.locator('.page-title')).toHaveText('训练建议', { timeout: 10_000 })
  // 4 类建议（字段镜像 services/training.ts；E2E-01 同源断言收紧到节点）
  await expect(page.getByText('正手击球点偏晚')).toBeVisible()
  await expect(
    page.getByText('正手拉冲多球训练：每组 30 球，共 3 组，固定高点期击球')
  ).toBeVisible()
  await expect(page.locator('.method-name').filter({ hasText: '多球训练' })).toBeVisible()
  // 推荐模板（training_plan_template=quick_improvement；section 标题收紧防 desc 子串误中）
  await expect(page.locator('.template-recommend-section .section-title')).toHaveText('📋 训练方案模板')
  await expect(page.locator('.recommend-code')).toHaveText('quick_improvement')

  // ── 模板列表：免费用户 → 40300 会员守卫 Empty 升级引导分支 ──
  await gotoPage(page, '/pages/training/templates/index')
  await expect(page.getByText('此功能需要会员')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('暂无训练模板')).toHaveCount(0) // 守卫分支非空态分支
  await page.getByRole('button', { name: '升级会员' }).click()
  await page.waitForURL(/membership/) // 守卫升级引导跳会员中心

  // ── 升级后（模拟支付开通）重进模板列表 → 模板可见 ──
  state.member = true
  // Taro H5 实测：hash 直跳复访已在页面栈中的路由时，新页面实例挂载并完成拉取
  // 但不前置（可见页仍为 membership）——改用带 query 的整页重载模拟「升级后
  // 重新进入」（全量 SPA 重启，页面栈清空，与真实用户升级后重进一致）
  await page.goto(`/?fresh=${Date.now()}#/pages/training/templates/index`)
  await page.waitForLoadState('networkidle')
  await expect(page.getByText('共 2 个模板')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('快速提升方案')).toBeVisible()

  // ── 模板详情四区（目标/训练内容/练习项目/检验指标）──
  // NutUI Cell 内部节点（.nut-cell-title）不参与 hit-test（探针实证 elementFromPoint
  // 在 title 中心返回 cell 根）——点击必须落在 cell 容器上（onClick 亦挂在 cell 根）
  await page.locator('.nut-cell.template-item').filter({ hasText: '快速提升方案' }).click()
  await page.waitForURL(/templates\/detail/, { timeout: 10_000 })
  await expect(page.getByText('训练目标')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.goal-metric')).toHaveText('正手拉冲成功率') // 目标 metric（检验指标同名收紧）
  await expect(page.getByText('多球拉冲')).toBeVisible() // 训练内容
  await expect(page.locator('.exercise-item').filter({ hasText: '正手拉冲' })).toBeVisible()
  // 检验指标收紧到 .metric-tag（goal metric「正手拉冲成功率」含同名子串）
  await expect(page.locator('.metric-tag').filter({ hasText: '正手拉冲成功率' })).toBeVisible()

  // ── 方案详情（plan_id deep link，镜像 progress summary Cell 跳转）──
  await gotoPage(page, `/pages/training/plans/detail/index?plan_id=${PLAN_ID}`)
  await expect(page.locator('.plan-header .page-title')).toBeVisible({ timeout: 10_000 })
  // 进度 1/2（训练单 #1 已完成）+ 待完成标记
  await expect(page.locator('.progress-text')).toHaveText('1 / 2')
  await expect(page.getByText('反手推挡稳定性')).toBeVisible()

  // ── 标记完成 → +5 积分 Toast（i18n 修复后文案）+ 进度 2/2 ──
  await page.getByRole('button', { name: '标记完成' }).click()
  await expect(
    page.locator('.taro__toast').getByText('训练单已完成，获得 5 积分')
  ).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.progress-text')).toHaveText('2 / 2', { timeout: 10_000 })

  // ── 重新评估（§7.4 步骤 8-9：触发方案调整 + 版本化记录）──
  const adjGet = page.waitForRequest((r) => r.url().includes('/adjustments'))
  await page.getByRole('button', { name: '重新评估' }).click()
  await expect(
    page.locator('.taro__toast').getByText('方案已重新评估')
  ).toBeVisible({ timeout: 10_000 })
  await adjGet // reEvaluatePlan 内刷新调整历史（fetchPlanAdjustments）

  // ── badge_unlocked WS 弹层（完成训练单触发，BadgeUnlockPopup）──
  const badgesRefresh = page.waitForRequest((r) => r.url().includes('/gamification/badges'))
  await pushWsMessage(page, {
    event: 'badge_unlocked',
    data: [{ badge_id: 'b_training_streak', name: '训练达人', icon: '🏅' }],
  })
  await expect(page.getByText('徽章解锁！')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.badge-unlock-item').filter({ hasText: '训练达人' })).toBeVisible()
  await expect(page.getByText('继续训练解锁更多徽章')).toBeVisible()
  await badgesRefresh // 弹层触发 fetchBadges 徽章列表刷新
})
