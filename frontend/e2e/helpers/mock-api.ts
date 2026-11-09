/**
 * E2E API mock 基建（FS8）
 * 以 page.route 拦截 `${BASE_URL}/**`（默认 https://api.pingpongai.com/api/v1），
 * 按「注册表 + 段级通配」分发；响应镜像后端统一 envelope
 * { code, message, data, timestamp }（app/core/response.py success()）。
 *
 * 反幻觉约束：mock 载荷字段与前端 service 镜像的后端 schema 逐字一致
 * （TierListData.tiers / QuotaData.remaining / NotificationItem.is_read 等）。
 */
import type { Page, Route } from '@playwright/test'

/** 端点通配模式：* 匹配单段（不含斜杠） */
export interface MockRoute {
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  /** 形如 /scoring/matches/{id段}/score（* 单段通配） */
  pattern: string
  /** 静态载荷（优先级低于 dynamic） */
  data?: unknown
  /** 动态载荷：params=通配捕获段，body=请求 JSON，callCount=同路由第几次调用 */
  dynamic?: (ctx: {
    params: string[]
    body: any
    query: URLSearchParams
    callCount: number
  }) => unknown
  /** HTTP 状态（非 200 时 envelope code 同步） */
  status?: number
  /** HTTP 200 + 业务错误码（如 40300 会员守卫） */
  envelopeCode?: number
}

/** 段级通配匹配；返回捕获段或 null */
export function matchPattern(pattern: string, path: string): string[] | null {
  const ps = pattern.split('/').filter(Boolean)
  const xs = path.split('/').filter(Boolean)
  if (ps.length !== xs.length) return null
  const params: string[] = []
  for (let i = 0; i < ps.length; i++) {
    if (ps[i] === '*') params.push(decodeURIComponent(xs[i]))
    else if (ps[i] !== xs[i]) return null
  }
  return params
}

function envelope(data: unknown, code = 0, message = 'ok') {
  return { code, message, data, timestamp: new Date().toISOString() }
}

/**
 * 安装 API mock。未注册的 /api/v1/** 返回 404 envelope（消息含端点，
 * 便于在控制台发现遗漏 mock）。
 */
export async function installApiMocks(page: Page, routes: MockRoute[]) {
  const counters = new Map<string, number>()
  page.on('console', (msg) => {
    if (msg.text().includes('unmocked')) console.log('  [unmocked]', msg.text())
  })
  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request()
    const method = req.method()
    const url = new URL(req.url())
    const m = url.pathname.match(/\/api\/v1(\/.*)$/)
    const path = m ? m[1] : url.pathname
    for (const r of routes) {
      const params = matchPattern(r.pattern, path)
      if (params && r.method === method) {
        const key = `${r.method} ${r.pattern}`
        const callCount = (counters.get(key) || 0) + 1
        counters.set(key, callCount)
        let body: any = null
        try {
          body = req.postDataJSON()
        } catch {
          body = null
        }
        if (r.status && r.status !== 200) {
          return route.fulfill({
            status: r.status,
            json: envelope(null, r.status, 'error'),
          })
        }
        const data = r.dynamic
          ? r.dynamic({ params, body, query: url.searchParams, callCount })
          : r.data
        if (r.envelopeCode) {
          return route.fulfill({
            status: 200,
            json: envelope(null, r.envelopeCode, 'business error'),
          })
        }
        return route.fulfill({ status: 200, json: envelope(data) })
      }
    }
    return route.fulfill({
      status: 404,
      json: envelope(null, 404, `unmocked ${method} ${path}`),
    })
  })
}
