/**
 * FS8-7 axe 无障碍全量扫描（@axe-core/playwright 已装，本 spec 接线）
 *
 * 范围：40 页全量 + onboarding 双页（新用户态二遍扫描，须清 completed 预置）。
 * 规则集：wcag2a + wcag2aa（契约化标签，避免默认规则漂移）。
 * 分级口径（04-前端实施计划 FS8-7）：critical/serious 阻塞（本 spec 门禁），
 * moderate/light 记入报告不阻塞（全量落地成本高，按计划入报告）。
 *
 * 扫描态说明：mock 走 baseMocks 通用首屏端点——部分页面专有端点 404 →
 * 渲染 error/empty/skeleton 兜底态（同样是真实可达状态，纳入扫描）。
 */
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { setup } from './helpers/auth'
import { a11yMocks } from './helpers/a11y-mocks'
import fs from 'node:fs'
import path from 'node:path'

interface ViolationSummary {
  page: string
  impact: string
  id: string
  help: string
  nodes: number
  /** 全部节点 target（修复定位用；超长截断） */
  targets: string[]
  /** 节点级证据：html 片段 + color-contrast 的 fg/bg/ratio/字号 */
  detail: Array<Record<string, unknown>>
}

/** [路径, query]——详情页参数镜像各页 router.params 读取（matchId camelCase 等） */
const PAGES: Array<[string, string]> = [
  ['/pages/home/index', ''],
  ['/pages/training/index', ''],
  ['/pages/match/index', ''],
  ['/pages/community/index', ''],
  ['/pages/user/profile/index', ''],
  ['/pages/user/edit/index', ''],
  ['/pages/user/big-data/index', ''],
  ['/pages/user/rating-history/index', ''],
  ['/pages/auth/login/index', ''],
  ['/pages/auth/consent/index', ''],
  ['/pages/video-analysis/upload/index', ''],
  ['/pages/video-analysis/processing/index', '?task_id=3'],
  ['/pages/video-analysis/report/index', '?report_id=7'],
  ['/pages/video-analysis/list/index', ''],
  ['/pages/dashboard/index', ''],
  ['/pages/match-data/quick-entry/index', ''],
  ['/pages/match-data/detailed-entry/index', ''],
  ['/pages/match-data/record-list/index', ''],
  ['/pages/match-data/record-detail/index', '?id=1'],
  ['/pages/scoring/setup/index', ''],
  ['/pages/scoring/scoreboard/index', '?matchId=1'],
  ['/pages/scoring/match-list/index', ''],
  ['/pages/scoring/statistics/index', '?matchId=1'],
  ['/pages/training/advice/index', ''],
  ['/pages/training/plans/detail/index', '?plan_id=8001'],
  ['/pages/training/templates/index', ''],
  ['/pages/training/templates/detail/index', '?id=101'],
  ['/pages/progress/comparison/index', '?report_a=6&report_b=7'],
  ['/pages/progress/summary/index', ''],
  ['/pages/progress/trend-detail/index', '?metric=loop_success_rate'],
  ['/pages/gamification/badges/index', ''],
  ['/pages/gamification/checkin-calendar/index', ''],
  ['/pages/membership/index', ''],
  ['/pages/payment/create/index', '?tier=member'],
  ['/pages/payment/orders/index', ''],
  ['/pages/notification/list/index', ''],
  ['/pages/settings/index', ''],
  // R-FE-R2（FE-P2-21）：协议 WebView 承载页——H5 走降级提示分支（weapp 分支 tree-shake）
  ['/pages/settings/webview/index', '?url=https%3A%2F%2Fexample.com%2Fterms&title=%E7%94%A8%E6%88%B7%E5%8D%8F%E8%AE%AE'],
]

test('FS8-7 axe 扫描：40 页 + onboarding 双态，critical/serious 零门禁', async ({ page }) => {
  test.setTimeout(300_000)
  const violations: ViolationSummary[] = []
  const pageStates: Array<{ page: string; text: string }> = []

  // onboarding completed 预置（规避 40 页扫描时首页引导跳转）；onboarding 路由本身
  // 跳过预置 → 第二遍整页重载即新用户态（init script 在 setup goto 前注册，先于 auth 脚本）
  await page.addInitScript(() => {
    if (!/#\/pages\/onboarding/.test(location.href)) {
      localStorage.setItem(
        'onboarding_progress',
        JSON.stringify({ data: JSON.stringify({ step: 'completed', completed: true }) })
      )
    }
  })
  await setup(page, a11yMocks, { auth: true, open: PAGES[0][0] })

  const collectAxe = async (route: string) => {
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze()
    for (const v of results.violations) {
      violations.push({
        page: route,
        impact: v.impact ?? 'unknown',
        id: v.id,
        help: v.help,
        nodes: v.nodes.length,
        targets: v.nodes.slice(0, 12).map((n) => (n.target ?? []).join(' ').slice(0, 100)),
        detail: v.nodes.slice(0, 12).map((n) => ({
          target: (n.target ?? []).join(' '),
          html: (n.html ?? '').slice(0, 140),
          // axe any[] 检查数据（color-contrast: fgColor/bgColor/contrastRatio/fontSize/fontWeight）
          data: (n.any ?? []).map((a) => a.data).filter(Boolean),
        })),
      })
    }
    const text = await page.evaluate(() =>
      (document.querySelector('#app')?.textContent ?? '').replace(/\s+/g, ' ').trim()
    )
    pageStates.push({ page: route, text: text.slice(0, 100) })
  }

  const scanPage = async (route: string, query: string) => {
    // 整页重载直达（复访规避 + 页面栈清空，E2E-04 实证口径）
    await page.goto(`/?fresh=${Date.now()}#${route}${query}`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(400) // Toast/Skeleton 消退缓冲
    await collectAxe(route)
  }

  // ── 第一遍：40 页（onboarding completed 预置，规避首页引导跳转）──
  for (const [route, query] of PAGES) {
    await scanPage(route, query)
  }

  // ── 第二遍：onboarding 双页新用户态 ──
  // 条件化 init script 对 #/pages/onboarding 路由跳过 completed 预置 →
  // 整页重载后 storage 为空 → 新用户（created_at=now）引导态真实渲染
  await scanPage('/pages/onboarding/index', '')
  await scanPage('/pages/onboarding/profile/index', '')

  // ── 报告落盘（全量 violation + 各页渲染态快照）──
  const reportPath = path.resolve('..', 'tmp', 'a11y-report.json')
  fs.mkdirSync(path.dirname(reportPath), { recursive: true })
  fs.writeFileSync(
    reportPath,
    JSON.stringify({ scanned: PAGES.length + 2, violations, pageStates }, null, 2),
    'utf-8'
  )

  // 控制台摘要（impact × 规则 聚合）
  const byImpact = new Map<string, number>()
  for (const v of violations) byImpact.set(v.impact, (byImpact.get(v.impact) ?? 0) + v.nodes)
  console.log('=== axe 摘要（violations × nodes，按 impact）===')
  console.log(JSON.stringify(Object.fromEntries(byImpact)))
  console.log(`报告已写入: ${reportPath}`)

  // ── 门禁：critical / serious 零容忍（moderate/light 入报告）──
  const blocking = violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
  console.log(
    `=== critical/serious: ${blocking.length} 条 ===`,
    JSON.stringify(blocking, null, 1)
  )
  expect(blocking, 'critical/serious violations 必须为零（明细见 a11y-report.json）').toEqual([])
})
