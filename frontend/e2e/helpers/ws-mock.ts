/**
 * E2E WebSocket mock（FS8 / E2E-02）
 *
 * 背景：Playwright page.route 无法拦截 ws:// 连接，而记分牌多设备同步的
 * 主通道是 WS（useMatchSync → score_update）。本 helper 在页面加载前以
 * MockWebSocket 替换 window.WebSocket（Taro H5 SocketTask 内部
 * `new WebSocket(url, protocols)`，@tarojs/taro-h5 SocketTask 构造实证），
 * 使 useWebSocket 视为「连接成功」，测试侧可：
 *   - 断言前端发送的帧（subscribe 协议，useMatchSync buildSubscribeMessage）
 *   - 主动注入服务端推送（score_update 广播），驱动设备 B 的
 *     applyWsScoreUpdate 乐观更新 + fetchMatch REST 对账双路径。
 *
 * 真机 <200ms 延迟指标属 FE-M1 联调验收（04-前端实施计划 §3.2），
 * mock E2E 验证行为编排与消息协议消费。
 */
import type { Page } from '@playwright/test'

/** 在页面加载前替换 window.WebSocket（须在首次 goto 前调用） */
export async function installWsMock(page: Page) {
  await page.addInitScript(() => {
    class MockWebSocket {
      url: string
      protocols: string[] | undefined
      readyState = 0
      onopen: ((ev?: unknown) => void) | null = null
      onmessage: ((ev: { data: unknown }) => void) | null = null
      onclose: ((ev?: unknown) => void) | null = null
      onerror: ((ev?: unknown) => void) | null = null

      constructor(url: string, protocols?: string[]) {
        this.url = url
        this.protocols = protocols
        const w = window as any
        w.__mockWsInstances.push(this)
        // 异步 open（对齐真实 WebSocket 时序，onOpen 赋值晚于构造）
        setTimeout(() => {
          this.readyState = 1
          this.onopen?.({ type: 'open' })
        }, 0)
      }

      send(data: unknown) {
        const w = window as any
        w.__mockWsSent.push(String(data))
      }

      close() {
        this.readyState = 3
        this.onclose?.({ type: 'close' })
      }

      // SocketTask 构造函数注册 addEventListener('close', ...)（taro-h5 实证）
      addEventListener(type: string, fn: (ev?: unknown) => void) {
        if (type === 'close') this.onclose = fn
        if (type === 'open') this.onopen = fn
        if (type === 'message') this.onmessage = fn as any
        if (type === 'error') this.onerror = fn
      }

      removeEventListener() {
        /* no-op */
      }
    }
    const w = window as any
    w.__mockWsInstances = []
    w.__mockWsSent = []
    w.MockWebSocket = MockWebSocket
    w.WebSocket = MockWebSocket
  })
}

/** 向页面注入一条服务端 WS 推送（{event, data}，镜像后端广播体） */
export async function pushWsMessage(page: Page, msg: unknown) {
  await page.evaluate((m) => {
    const ws = (window as any).__mockWsInstances?.[0]
    ws?.onmessage?.({ data: JSON.stringify(m) })
  }, msg)
}

/** 读取页面经 WS 发送的全部帧（subscribe 协议断言用） */
export async function getWsSent(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as any).__mockWsSent || [])
}

/** 模拟服务端断连（onerror + close → 前端应显示断线横幅并指数退避重连） */
export async function dropWsConnection(page: Page) {
  await page.evaluate(() => {
    const ws = (window as any).__mockWsInstances?.[0]
    ws?.onerror?.({ type: 'error' })
    ws?.onclose?.({ type: 'close', code: 1006 })
  })
}
