/**
 * E2E-05 通知交互全流程（docs/07实施计划/02-测试计划.md §7.5 / FS8-6）
 * 首页铃铛未读角标 → 通知列表三态筛选 → 点击标记已读 → 全部已读 →
 * WS notification 实时头插（负时间戳 id）+ export_completed 幂等角标刷新。
 *
 * 关键实现口径：
 * - 入口取首页（NotificationBell 挂 home TopBar，FS6 单一挂载点）→ 预置
 *   onboarding_progress=completed 规避新用户引导跳转（E2E-01 主线已覆盖引导流）
 * - export_completed WS（useWebSocket.handleBuiltinEvent 内置四事件之一）→
 *   fetchUnreadCount 幂等刷新角标（不落库，12-notification/frontend.md §4）
 * - WS notification 事件头插由本地 store 消化（负时间戳 id 合成），
 *   unreadCount 本地 +1 → 铃铛角标实时跟随（不入 mock 状态）
 * - NutUI Cell 内部节点不参与 hit-test（::before 覆盖层，E2E-04 探针实证）→
 *   列表项点击落在 cell 根；Tabs 点击落在 .nut-tabs-titles-item
 */
import { test, expect } from '@playwright/test'
import { setup } from './helpers/auth'
import { installWsMock, pushWsMessage } from './helpers/ws-mock'
import { createNotificationMocks } from './helpers/notification-mocks'

test('E2E-05 通知交互：铃铛角标→三态筛选→标记已读→全部已读→WS 实时头插+角标刷新', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const { routes } = createNotificationMocks()

  await installWsMock(page)

  // 预置登录态 + onboarding 已完成（Taro H5 storage {data} 信封 + store JSON.parse 双层）
  await page.addInitScript(() => {
    localStorage.setItem(
      'onboarding_progress',
      JSON.stringify({ data: JSON.stringify({ step: 'completed', completed: true }) })
    )
  })

  // ── 首页：铃铛未读角标 2（初始 unread=2）──
  await setup(page, routes, { auth: true, open: '/pages/home/index' })
  await expect(page.locator('.notif-bell-badge')).toHaveText('2', { timeout: 15_000 })

  // ── export_completed WS → 幂等刷新未读数（角标不变，断言 unread-count 拉取）──
  const unreadRefresh = page.waitForRequest((r) => r.url().includes('/notification/unread-count'))
  await pushWsMessage(page, { event: 'export_completed', data: {} })
  await unreadRefresh
  await expect(page.locator('.notif-bell-badge')).toHaveText('2')

  // ── 点击铃铛 → 通知列表（3 条，2 未读点 + 全部已读按钮可见）──
  await page.locator('.notif-bell').click()
  await page.waitForURL(/notification\/list/, { timeout: 10_000 })
  await expect(page.locator('.notification-header-title')).toHaveText('通知中心', { timeout: 10_000 })
  await expect(page.locator('.nut-cell.notification-item')).toHaveCount(3)
  await expect(page.locator('.unread-dot')).toHaveCount(2)
  await expect(page.getByRole('button', { name: '全部已读' })).toBeVisible()
  // 未读项 unread 类 + 已读项无点（5003 score_update）
  await expect(
    page.locator('.nut-cell.notification-item.unread').filter({ hasText: '分析报告已生成' })
  ).toBeVisible()
  await expect(
    page.locator('.nut-cell.notification-item:not(.unread)').filter({ hasText: '比赛比分已更新' })
  ).toBeVisible()

  // ── 三态筛选：未读 Tab → is_read=false（2 条）──
  const unreadReq = page.waitForRequest((r) => r.url().includes('is_read=false'))
  await page.locator('.nut-tabs-titles-item').filter({ hasText: '未读' }).click()
  await unreadReq
  await expect(page.locator('.nut-cell.notification-item')).toHaveCount(2, { timeout: 10_000 })
  await expect(page.getByText('徽章解锁：训练达人')).toBeVisible()
  await expect(page.getByText('比赛比分已更新')).toHaveCount(0)

  // ── 已读 Tab → is_read=true（1 条）──
  const readReq = page.waitForRequest((r) => r.url().includes('is_read=true'))
  await page.locator('.nut-tabs-titles-item').filter({ hasText: '已读' }).click()
  await readReq
  await expect(page.locator('.nut-cell.notification-item')).toHaveCount(1, { timeout: 10_000 })
  await expect(page.getByText('比赛比分已更新')).toBeVisible()

  // ── 全部 Tab → 3 条复原 ──
  await page.locator('.nut-tabs-titles-item').filter({ hasText: '全部' }).click()
  await expect(page.locator('.nut-cell.notification-item')).toHaveCount(3, { timeout: 10_000 })

  // ── 点击未读项（无 action_url → 仅标记已读，POST 体逐字断言）──
  const readPost = page.waitForRequest(
    (r) =>
      r.url().includes('/notification/read') &&
      r.method() === 'POST' &&
      JSON.parse(r.postData() ?? '{}').notification_ids?.[0] === 5001
  )
  await page
    .locator('.nut-cell.notification-item')
    .filter({ hasText: '分析报告已生成' })
    .click()
  await readPost
  // 本地态联动：未读点 2→1，全部已读按钮仍可见（unreadCount=1 > 0）
  await expect(page.locator('.unread-dot')).toHaveCount(1, { timeout: 10_000 })
  await expect(
    page.locator('.nut-cell.notification-item:not(.unread)').filter({ hasText: '分析报告已生成' })
  ).toBeVisible()

  // ── 全部已读 → unreadCount 0：按钮隐藏、未读点清零、列表页脚注出现 ──
  await page.getByRole('button', { name: '全部已读' }).click()
  await expect(page.locator('.unread-dot')).toHaveCount(0, { timeout: 10_000 })
  await expect(page.getByRole('button', { name: '全部已读' })).toHaveCount(0)

  // ── WS notification 实时头插：负时间戳 id 合成 + unreadCount 0→1 ──
  // （后端在线直推 {type,title,content,extra_data}，useWebSocket 合成后 store 头插）
  await pushWsMessage(page, {
    event: 'notification',
    data: {
      type: 'training_reminder',
      title: '训练提醒：今日训练单未完成',
      content: '尽快完成今日训练计划，保持连胜！',
      extra_data: null,
    },
  })
  // 新通知居首 + 未读点复现 + 全部已读按钮随 unreadCount>0 复现
  await expect(
    page.locator('.notification-items .nut-cell.notification-item').first()
  ).toContainText('训练提醒：今日训练单未完成', { timeout: 10_000 })
  await expect(
    page.locator('.nut-cell.notification-item.unread').filter({ hasText: '训练提醒：今日训练单未完成' })
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '全部已读' })).toBeVisible()

  // ── 返回首页：铃铛角标实时跟随 store.unreadCount = 1 ──
  await page.goBack()
  await expect(page.locator('.notif-bell-badge')).toHaveText('1', { timeout: 10_000 })
})
