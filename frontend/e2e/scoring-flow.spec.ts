/**
 * E2E-02 记分牌全流程（docs/07实施计划/02-测试计划.md §7.2）
 * 创建比赛（bo3）→ 开始 → 设备 A 记分 → 设备 B WS 同步 → 撤销 →
 * 记分到目标分（11）→ 结束 → 统计 → 看板记录联动。
 *
 * 多设备同步（步骤 3-5）实现口径：
 * - WS 不可 route 拦截 → helpers/ws-mock 以 MockWebSocket 替换 window.WebSocket，
 *   两台「设备」（page/pageB）各自建立 mock 连接；
 * - 设备 A 记分命中 REST mock（共享 matchState）后，测试侧模拟后端向设备 B
 *   广播 score_update（镜像 ScoringService.score 广播体）→ B 走
 *   applyWsScoreUpdate 乐观更新 + fetchMatch REST 对账双路径；
 * - 订阅协议断言：B 连接后应发送 {event:'subscribe', match_id}（后端 ws.py
 *   receive_loop 协议，R12-SC-2）；
 * - <200ms 延迟指标属 FE-M1 真机联调验收，mock E2E 验证行为编排与协议消费。
 *
 * 记分序列（bo3，target 11）：
 * user×2（正手拉球/发球得分）→ opp×1（对手失误）→ B 同步 2:1 →
 * 撤销 opp 球（2:0，序号 3→2）→ B 同步回退 → user×9（正手攻球）达 11:0
 * 局 1 结束（bo3 需 2 胜 → 比分清零进入局 2）→ 手动结束（局分 1:0 胜）→
 * 统计页（得分分布/技术动作/总得分）→ 看板比赛记录出现该场胜利。
 */
import { test, expect, type Page } from '@playwright/test'
import { setup } from './helpers/auth'
import { installWsMock, pushWsMessage, getWsSent } from './helpers/ws-mock'
import { createScoringMocks } from './helpers/scoring-mocks'

const OPPONENT_NAME = '王教练'

/** 设备 A 记一次分：点大按钮 → 得分方式弹窗选方式 */
async function scorePoint(page: Page, scorer: 'user' | 'opponent', methodLabel: string) {
  await page.getByRole('button', { name: scorer === 'user' ? '我得分' : '对手得分' }).click()
  await page.getByRole('button', { name: methodLabel, exact: true }).click()
}

/**
 * weui-picker 滚轮拖选。taro H5 Picker 滚轮（taro-picker-group Stencil 组件）
 * 同时监听 mouse 与 touch 事件（onMouseDown/mousemove/mouseup 驱动同一
 * handleMoveStart/Moving/End 链）——Playwright 鼠标拖动即可（TouchEvent
 * 构造与 CDP dispatchTouchEvent 在该组件上均未触发 handler，实证无效）。
 * LINE_HEIGHT=34（picker 源码常量）：向下拖一格 = 选中前一项。
 */
async function dragPickerWheel(page: Page, deltaY: number) {
  // 等待弹层动画稳定（点击触发后 modal 有 ~300ms transition，立即拖动坐标失效）
  await page.locator('.weui-picker__group').first().waitFor({ state: 'visible' })
  await page.waitForTimeout(400)
  const box = await page.locator('.weui-picker__group').first().boundingBox()
  if (!box) throw new Error('weui-picker__group not found')
  const x = box.x + box.width / 2
  const y = box.y + box.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x, y + deltaY, { steps: 6 })
  await page.mouse.up()
  // 吸附动画（transition 0.3s）后再确认
  await page.waitForTimeout(400)
}

test('E2E-02 记分牌全流程：创建→记分→多设备WS同步→撤销→目标分→结束→统计→看板', async ({
  page,
  context,
}) => {
  test.setTimeout(150_000)
  const { routes, state } = createScoringMocks()

  // ── 步骤 1：设备 A 创建比赛（bo3）──
  await installWsMock(page)
  await setup(page, routes, { auth: true, open: '/pages/scoring/setup/index' })
  await page.locator('input[placeholder="请输入对手姓名"]').fill(OPPONENT_NAME)
  // 赛制默认 bo5（idx2）→ 选 bo3（idx1，测试计划 §7.2 步骤 1）：滚轮向下拖一格
  //（两枚 Picker 的弹层均常驻 DOM，取 DOM 序第一枚 = 赛制 Picker 的「确定」）
  await page.locator('.picker-value').first().click()
  await dragPickerWheel(page, 34)
  await page.getByText('确定').first().click()
  await expect(page.locator('.picker-value').first()).toHaveText('3局2胜')
  await page.getByRole('button', { name: '开始比赛' }).click()

  // ── 步骤 2：跳转记分页，setup 态自动 start（X-21）→ in_progress ──
  await page.waitForURL(/matchId=4001/, { timeout: 10_000 })
  // 记分页骨架解除后渲染比分（0:0）+ WS mock 连接成功（断线横幅不出现）
  await expect(page.locator('.score-user .score-number')).toHaveText('0', { timeout: 10_000 })
  await expect(page.locator('.score-opp .score-number')).toHaveText('0')
  await expect(page.getByText('连接已断开，正在重连...')).toHaveCount(0)

  // ── 设备 B 挂载（比赛已创建）：mock WS + 登录态直达记分页 ──
  const pageB = await context.newPage()
  await installWsMock(pageB)
  await setup(pageB, routes, {
    auth: true,
    open: '/pages/scoring/scoreboard/index?matchId=4001',
  })
  await expect(pageB.locator('.score-user .score-number')).toHaveText('0', { timeout: 10_000 })
  // 订阅协议（后端 ws.py receive_loop：{event:'subscribe', match_id}）
  const sentB = await getWsSent(pageB)
  expect(sentB.some((s) => s.includes('"subscribe"') && s.includes('"match_id":4001'))).toBe(true)

  // ── 步骤 3：设备 A 记分（含得分方式标记，SCOR-U-07）──
  await scorePoint(page, 'user', '正手拉球') // rally_point + forehand_loop
  await expect(page.locator('.score-user .score-number')).toHaveText('1')
  await scorePoint(page, 'user', '发球得分') // serve_point
  await expect(page.locator('.score-user .score-number')).toHaveText('2')
  await scorePoint(page, 'opponent', '对手失误') // opponent_error
  await expect(page.locator('.score-opp .score-number')).toHaveText('1')

  // ── 步骤 4：设备 B WS 同步（模拟后端 score_update 广播）──
  const m = state.match!
  await pushWsMessage(pageB, {
    event: 'score_update',
    data: {
      match_id: m.id,
      sequence: m.seq,
      score: `${m.score_user}:${m.score_opp}`,
      scorer: 'opponent',
      score_method: 'opponent_error',
      current_server: m.current_server,
      is_key_point: false,
    },
  })
  // B 乐观更新 + fetchMatch 对账 → 比分与 A 一致（2:1，序号一致）
  await expect(pageB.locator('.score-user .score-number')).toHaveText('2', { timeout: 10_000 })
  await expect(pageB.locator('.score-opp .score-number')).toHaveText('1')
  await expect(pageB.getByText('连接已断开，正在重连...')).toHaveCount(0)

  // ── 步骤 5：撤销最近一球（序号回退 + 广播）──
  await page.getByRole('button', { name: '撤销' }).click()
  await expect(page.locator('.score-opp .score-number')).toHaveText('0')
  // 撤销也广播（后端 undo 推 score_update type:'undo'）→ B 对账回退
  await pushWsMessage(pageB, {
    event: 'score_update',
    data: { match_id: m.id, sequence: m.seq, score: `${m.score_user}:${m.score_opp}`, type: 'undo' },
  })
  await expect(pageB.locator('.score-opp .score-number')).toHaveText('0', { timeout: 10_000 })

  // ── 步骤 6：记分到目标分（11 分拿局；bo3 局 1 结束 → 比分清零进入局 2）──
  for (let i = 0; i < 9; i++) {
    await scorePoint(page, 'user', '正手攻球') // rally_point + forehand_drive
  }
  // 局 1 达 11:0 → game_ended → games_won_user=1（bo3 需 2）→ 局 2 比分 0:0
  await expect(page.locator('.score-user .score-number')).toHaveText('0', { timeout: 10_000 })
  await expect(page.locator('.score-opp .score-number')).toHaveText('0')

  // ── 步骤 7：结束比赛（状态机 in_progress → finished）──
  await page.getByRole('button', { name: '结束比赛' }).first().click()
  await expect(page.getByText('确认结束比赛？')).toBeVisible()
  // Dialog confirm 与操作栏按钮同名 → 取最后渲染的（Dialog teleport 至 body 尾部）
  await page.getByRole('button', { name: '结束比赛' }).last().click()

  // ── 步骤 8：自动跳转统计页（局分 1:0 胜）──
  await page.waitForURL(/scoring\/statistics/, { timeout: 10_000 })
  await expect(page.getByText('胜利')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.result-score')).toHaveText('1:0')
  await expect(page.getByText('VS 王教练')).toBeVisible()
  // 得分分布（记分序列：rally_point 10 + serve_point 1；opp 球已撤销；
  // 数值断言收紧到 .dist-count 节点 + 全等正则，防「11」子串误中「1」）
  await expect(page.locator('.distribution-list').getByText('相持得分')).toBeVisible()
  await expect(page.locator('.distribution-list .dist-count').filter({ hasText: /^10$/ })).toBeVisible()
  await expect(page.locator('.distribution-list').getByText('发球得分')).toBeVisible()
  await expect(page.locator('.distribution-list .dist-count').filter({ hasText: /^1$/ })).toBeVisible()
  // 技术动作分解（正手攻球 9 / 正手拉球 1）
  await expect(page.locator('.technique-list').getByText('正手攻球')).toBeVisible()
  await expect(page.locator('.technique-list .dist-count').filter({ hasText: /^9$/ })).toBeVisible()
  await expect(page.locator('.technique-list').getByText('正手拉球')).toBeVisible()
  // 总得分（撤销后 11 球）
  await expect(page.getByText('总得分: 11')).toBeVisible()

  // ── 步骤 9/10：看板联动（比赛记录出现本场胜利；级联积分/打卡由后端 627 用例覆盖）──
  await page.goto('/#/pages/dashboard/index')
  await page.waitForLoadState('networkidle')
  // 页内标题 .dashboard-title（导航栏同名 title 在 H5 为隐藏元素，getByText 会误中）
  await expect(page.locator('.dashboard-title')).toBeVisible({ timeout: 10_000 })
  // 比赛记录卡：vs 王教练 + 局分 1 - 0 + 胜
  await expect(page.getByText('vs 王教练')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.record-score').filter({ hasText: '1 - 0' })).toBeVisible()
  await expect(page.locator('.record-result').filter({ hasText: '胜' })).toBeVisible()
})
