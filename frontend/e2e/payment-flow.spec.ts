/**
 * E2E-03 付费转化全流程（docs/07实施计划/02-测试计划.md §7.3）
 * 免费额度用尽 → 购买会员 → 支付 → 权益生效 → 无限分析。
 *
 * 关键实现口径（02-测试计划 §7.3 九步）：
 * - 步骤 1「免费分析 3 次」：REST 状态机预置 used_today=3（/users/quota 免费视图，
 *   后端 user_service.get_quota 不感知会员态）
 * - 步骤 2「第 4 次尝试 429/42910」：POST /video-analysis/tasks 免费态返回
 *   HTTP 429 + code 42910（后端 AppException 消息逐字镜像），上传页 NutUI Toast
 *   展示 err.message（request.ts createRequestError 透传）
 *   R-FE-R1 批次B（FE-P1-4/10）：429/42910 差异化交互落地后，上传页
 *   弹升级引导弹层（useMembershipGate；免费态进入页面时额度耗尽亦主动弹），
 *   「立即升级」直达会员中心——本 spec 经弹层走真实转化路径（取代手动 navigateTo 旁路）
 * - 步骤 5「微信支付（mock）」：H5 生产产物 taro-h5 requestPayment 为
 *   temporarilyNotSupport → NODE_ENV=production 下 resolve（requestWechatPay=true），
 *   真实 JSAPI 拉起归 FS8-11 真机联调
 * - 步骤 6「支付成功」：create 页 handlePay Toast 唯一出口 + pollOrderStatus
 *   降级轮询（payment_success WS 未达/微信回调延迟场景）——mock 模拟回调在
 *   2s 轮询窗内到达（GET /payment/orders 首查翻 paid），确认后 refreshAll
 *   权益即时刷新（FS8-4 验收：pollOrderStatus 降级轮询路径覆盖）
 * - 步骤 9「验证级联」：WS payment_success 推送 → usePaymentNotify（orders 页挂载）
 *   fetchOrders 列表刷新（审计日志为后端域，627 用例覆盖）
 */
import { test, expect } from '@playwright/test'
import { setup, gotoPage } from './helpers/auth'
import { installWsMock, pushWsMessage } from './helpers/ws-mock'
import { recordSampleVideo } from './helpers/record-video'
import { createPaymentMocks } from './helpers/payment-mocks'

test('E2E-03 付费转化全流程：额度尽→429→会员对比→下单→JSAPI→paid→权益刷新→第4次分析→订单', async ({
  page,
}) => {
  test.setTimeout(150_000)
  const { routes, state } = createPaymentMocks()

  // WS mock：会员页/订单页 usePaymentNotify 共享连接（payment_success 消费断言）
  await installWsMock(page)

  // ── 步骤 1：免费额度 3/3 用尽（upload 页额度提示 + 升级引导弹层）──
  await setup(page, routes, { auth: true, open: '/pages/video-analysis/upload/index' })
  await expect(page.getByText('拍摄引导')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('今日免费额度剩余 0 次')).toBeVisible()
  // R-FE-R1 批次B（FE-P1-10①）：免费用户额度耗尽进入页面 → 主动弹升级提示
  await expect(page.getByText('免费额度已用完')).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: '暂不升级' }).click() // 关闭弹层继续验证 429 路径

  // ── 步骤 2：第 4 次尝试 → 429/42910 Toast（后端消息逐字）+ 升级引导弹层 ──
  const sample = await recordSampleVideo(page)
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: '选择/拍摄视频' }).click()
  const chooser = await chooserPromise
  await chooser.setFiles({ name: sample.name, mimeType: sample.mimeType, buffer: sample.buffer })
  await expect(
    page.getByText('今日免费分析次数已用完，升级会员可无限分析')
  ).toBeVisible({ timeout: 15_000 })
  // 失败后 resetUpload 回 idle：上传入口仍在（不卡在 uploading 态）
  await expect(page.getByRole('button', { name: '选择/拍摄视频' })).toBeVisible()
  // R-FE-R1 批次B（FE-P1-4）：429/42910 差异化交互 → 升级引导弹层承接转化
  await expect(page.getByText('免费额度已用完')).toBeVisible({ timeout: 10_000 })

  // ── 步骤 3：弹层「立即升级」→ 会员中心四级对比（免费/会员/专业/教练 + 定价 + 免费额度卡）──
  // （R-FE-R1：取代手动 gotoPage 旁路——走 handleUpgradeConfirm 真实转化路径）
  await page.getByRole('button', { name: '立即升级' }).click()
  await page.waitForURL(/membership/, { timeout: 10_000 })
  await expect(page.getByText('会员等级权益对比')).toBeVisible({ timeout: 10_000 })
  // 四级表头（tier-name 节点收紧，防误中「会员等级权益对比」标题）
  for (const name of ['免费版', '会员版', '专业版', '教练版']) {
    await expect(page.locator('.tier-table .tier-name').filter({ hasText: name })).toBeVisible()
  }
  // 定价：会员 ¥18/月（后端 tiers 分定价，i18n priceMonthly）；免费档显示「免费」
  await expect(page.locator('.tier-table .tier-price').filter({ hasText: '¥18/月' })).toBeVisible()
  await expect(page.locator('.tier-table .tier-price').filter({ hasText: '免费' })).toBeVisible()
  // 当前态：免费用户 + 免费额度卡 remaining 0 / 已用 3
  await expect(page.locator('.current-status .status-text')).toHaveText('免费用户')
  await expect(page.locator('.quota-card .quota-number')).toHaveText('0')
  await expect(page.getByText('今日已用 3 次')).toBeVisible()

  // ── 步骤 4：member 列「开通会员」→ 支付页（?tier=member 带入）──
  await page
    .locator('.action-row .tier-cell')
    .nth(1)
    .getByRole('button', { name: '开通会员' })
    .click()
  await page.waitForURL(/payment\/create/, { timeout: 10_000 })
  await expect(page.getByText('选择适合您的会员等级')).toBeVisible({ timeout: 10_000 })
  // 定价动态来自后端 tiers（formatAmount 分→元两位小数）；member 默认选中（query 带入）
  await expect(page.locator('.tier-card.selected')).toContainText('会员版')
  await expect(page.locator('.amount-value')).toHaveText('¥18.00')
  await expect(page.getByText('月卡')).toBeVisible()

  // ── 步骤 5：微信支付（mock JSAPI）→ 创建订单（契约：POST 体逐字断言）──
  const orderReq = page.waitForRequest(
    (req) => req.url().includes('/payment/orders') && req.method() === 'POST'
  )
  await page.getByRole('button', { name: '微信支付' }).click()
  const req = await orderReq
  expect(req.postDataJSON()).toEqual({
    product_type: 'membership',
    tier: 'member',
    period: 'monthly',
    payment_method: 'wechat_jsapi',
  })
  // 支付成功 Toast（taro-h5 .taro__toast；生产产物 requestPayment resolve → true）
  await expect(page.locator('.taro__toast').getByText('支付成功')).toBeVisible({ timeout: 5_000 })

  // ── 步骤 6/7：pollOrderStatus 轮询确认 paid（2s 窗内回调到达）→
  //    navigateBack 回会员页 → 权益即时刷新（member/active/剩余20天，免费额度卡隐藏）──
  await page.waitForURL(/membership/, { timeout: 15_000 })
  await expect(page.locator('.tier-badge-text')).toHaveText('MEMBER', { timeout: 15_000 })
  await expect(page.locator('.current-tier-name')).toHaveText('会员版')
  await expect(page.locator('.current-status .status-text')).toHaveText('有效中')
  await expect(page.getByText('剩余20天')).toBeVisible()
  await expect(page.locator('.quota-card')).toHaveCount(0) // 免费额度卡仅 free 展示

  // ── 步骤 8：第 4 次分析放行（会员跳过额度检查，S5）──
  await gotoPage(page, '/pages/video-analysis/upload/index')
  await expect(page.getByText('拍摄引导')).toBeVisible({ timeout: 10_000 })
  // /users/quota 为免费视图（后端 get_quota 不感知会员态）——展示 0 是后端契约
  await expect(page.getByText('今日免费额度剩余 0 次')).toBeVisible()
  // R-FE-R1 批次B（FE-P1-10①）：会员态不弹升级引导（quota 免费视图防误弹判定）。
  // gotoPage 为同文档 hash 导航——Taro 页栈复用原 upload 实例，其弹层历经
  // 两开两关后按 NutUI unmountOnExit=false 以隐藏 DOM 留存（count 恒 ≥1），
  // 故断言不可见（误弹为可见态时仍失败，守卫语义不变）而非 count=0
  await expect(page.getByText('免费额度已用完')).toBeHidden()
  const sample2 = await recordSampleVideo(page)
  const chooserPromise2 = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: '选择/拍摄视频' }).click()
  const chooser2 = await chooserPromise2
  await chooser2.setFiles({ name: sample2.name, mimeType: sample2.mimeType, buffer: sample2.buffer })
  // 创建成功 → 跳转进度页（upload 页 redirectTo，修复前免费态在此被 429 拦截）
  await page.waitForURL(/task_id=3/, { timeout: 20_000 })
  await expect(page.getByText('AI 正在分析你的视频...')).toBeVisible({ timeout: 10_000 })

  // ── 步骤 9：订单列表（paid 单）+ 级联 WS payment_success → 列表刷新 ──
  await gotoPage(page, '/pages/payment/orders/index')
  await expect(page.getByText('会员订阅').first()).toBeVisible({ timeout: 10_000 })
  const order = state.order!
  expect(order.status).toBe('paid')
  await expect(page.getByText(order.order_no)).toBeVisible()
  await expect(page.locator('.order-card').first()).toContainText('已支付')
  await expect(page.locator('.order-card').first()).toContainText('¥18.00')
  await expect(page.locator('.order-card').first()).toContainText('会员已生效')

  // WS payment_success 推送 → usePaymentNotify fetchOrders（列表刷新级联）
  const wsRefresh = page.waitForRequest(
    (r) => r.url().includes('/payment/orders') && r.method() === 'GET'
  )
  await pushWsMessage(page, {
    event: 'payment_success',
    data: { order_id: order.id, product_type: 'membership' },
  })
  await wsRefresh
})
