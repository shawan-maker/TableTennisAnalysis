/**
 * useWebSocket — 统一 WebSocket Hook（总览 §3.3/§3.6；12-notification/frontend.md §4 单例模型）
 *
 * - 连接地址：buildWsUrl()（wss://api.pingpongai.com/ws / ws://localhost:8000/ws）
 * - 认证：Sec-WebSocket-Protocol 子协议 `jwt.{access_token}`（API §14.1 P2 安全合规；
 *   Token 不进 URL，避免日志/代理缓存/Referer 泄露；后端 ws.py Step 0 实现一致）
 * - 指数退避重连：1 → 2 → 4 → 8 → 16s，最大 5 次（禁止固定间隔）
 * - 30s 心跳 ping 维持连接活性；pong 返回 token_expired=true 时自动刷新 Token 并重建连接（API §14.2）
 * - 重连成功后回调 onReconnect() 拉取断连期间错过的消息（后端 on_ws_reconnect 推 sync）
 *
 * FS6-P3 单例化（12-notification §4 connectionCount + sharedListeners）：
 * FS1 初版为每 Hook 实例独占一条连接——FS6 起 BadgeUnlockPopup / 通知铃铛 /
 * 支付成功监听多域 Hook 并存，按设计 §4 重构为模块级共享单例：首个消费者挂载
 * 建立连接，最后一个卸载才关闭；各 Hook 的 onMessage/onReconnect 以监听器集合
 * 形式共享分发。API 向后兼容（useBadgeUnlock / useAnalysisProgress / useMatchSync 零改动）。
 *
 * FS6-P3 内置通知域事件（设计 §4 样例的 switch 分发形态，连接级单次执行，
 * 避免多页面共存时铃铛/列表页重复 addNotification 导致未读数翻倍）：
 * - connected → setWsConnected(true)（后端 ws.py Step 3 连接欢迎事件）
 * - notification → addNotification（后端在线用户直推 {type,title,content,extra_data}，
 *   无 id/is_read/created_at，此处合成完整 item；负时间戳 id 防与 DB 主键冲突）
 * - sync → setUnreadCount(data.unread_count)（后端 on_ws_reconnect 重连补偿，
 *   data 直接携带未读数；缺失时回退 fetchUnreadCount）
 * - export_completed → fetchUnreadCount()（实施计划 FS6 角标三事件之一；
 *   后端 tasks/user.py L216 直推不落库，幂等刷新角标）
 * - membership_downgrade → membershipStore.refreshAll()（10-membership §9：
 *   后端 Beat 到期降级任务推送，静默刷新当前会员状态/额度）
 * - 其余事件（badge_unlocked / payment_success / analysis_* / score_update 等）
 *   → sharedListeners 分发，由领域 Hook 消费。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { useAuthStore } from '@/stores/authStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { useMembershipStore } from '@/stores/membershipStore'

const RECONNECT_DELAYS = [1, 2, 4, 8, 16] // 秒，指数退避
const HEARTBEAT_INTERVAL = 30000 // 30s

export interface WsMessage {
  event?: string
  data?: any
  [key: string]: any
}

export interface UseWebSocketOptions {
  /** 收到消息（已尝试 JSON 解析；内置事件 connected/notification/sync/export_completed/membership_downgrade 已消化不再分发） */
  onMessage?: (msg: WsMessage) => void
  /** 连接/重连成功后回调（拉取断连期间消息） */
  onReconnect?: () => void
}

// ── 模块级共享单例状态（多 Hook 实例共享同一连接）──
type Listener = { onMessage?: (msg: WsMessage) => void; onReconnect?: () => void }

let sharedSocketTask: Promise<any> | null = null
let connectionCount = 0
const sharedListeners = new Set<Listener>()
const connectedSubscribers = new Set<(connected: boolean) => void>()
let sharedConnected = false
let isManualClose = false // 模块级：避免实例卸载后 onClose 捕获 stale 状态导致僵尸重连
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let reconnectAttempt = 0
let pendingReconnectTimer: ReturnType<typeof setTimeout> | null = null

/** 构造 WS 连接地址（Token 不进 URL，走 Sec-WebSocket-Protocol 子协议，API §14.1） */
export function buildWsUrl(): string {
  return process.env.TARO_APP_WS || 'wss://api.pingpongai.com/ws'
}

/** 广播连接状态到所有订阅者 */
function notifyConnected(connected: boolean) {
  sharedConnected = connected
  useNotificationStore.getState().setWsConnected(connected)
  connectedSubscribers.forEach((fn) => fn(connected))
}

function cleanupHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

/**
 * 内置通知域事件处理（连接级单次执行，设计 §4 switch 分发形态）。
 * 返回 true 表示已消化，不再向 sharedListeners 分发。
 * （导出供协议测试：connected/notification/sync/export_completed/membership_downgrade
 *  五事件消费契约）
 */
export function handleBuiltinEvent(msg: WsMessage): boolean {
  const store = useNotificationStore.getState()
  switch (msg.event) {
    case 'connected':
      // 后端 ws.py Step 3 连接欢迎事件
      store.setWsConnected(true)
      return true
    case 'notification': {
      // 后端在线用户直推 {type,title,content,extra_data}（无 id/is_read/created_at）
      const wsData = msg.data || {}
      store.addNotification({
        id: -Date.now(),
        type: wsData.type ?? 'system',
        title: wsData.title ?? '',
        content: wsData.content ?? null,
        is_read: false,
        extra_data: wsData.extra_data ?? null,
        created_at: new Date().toISOString(),
      })
      return true
    }
    case 'sync': {
      // 后端 on_ws_reconnect 重连补偿：data 直接携带 unread_count
      const count = msg.data?.unread_count
      if (typeof count === 'number') {
        store.setUnreadCount(count)
      } else {
        store.fetchUnreadCount()
      }
      return true
    }
    case 'export_completed':
      // 实施计划 FS6 角标三事件之一（后端直推不落库，幂等刷新角标）
      store.fetchUnreadCount()
      return true
    case 'membership_downgrade':
      // 后端 Beat 到期降级任务推送（10-membership §9：刷新会员状态/额度）
      useMembershipStore.getState().refreshAll()
      return true
    default:
      return false
  }
}

/** 指数退避重连: 1→2→4→8→16s，最大 5 次 */
function scheduleReconnect() {
  if (reconnectAttempt >= RECONNECT_DELAYS.length) return
  if (connectionCount === 0) return // 已无消费者：不重连
  const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)]
  reconnectAttempt++
  pendingReconnectTimer = setTimeout(() => {
    pendingReconnectTimer = null
    sharedSocketTask = null
    connectShared()
  }, delay * 1000)
}

/** 建立共享连接（幂等：已有连接直接返回） */
function connectShared() {
  if (sharedSocketTask) return
  const token = useAuthStore.getState().accessToken
  if (!token) return // 无 Token 不连接，由登录流程就绪后重建
  isManualClose = false
  // Sec-WebSocket-Protocol 子协议认证（API §14.1 P2 / 后端 ws.py Step 0）
  const taskPromise: Promise<any> = Taro.connectSocket({
    url: buildWsUrl(),
    protocols: [`jwt.${token}`],
  })
  sharedSocketTask = taskPromise

  taskPromise
    .then((task) => {
      if (isManualClose) {
        try {
          task?.close?.({})
        } catch {
          // 忽略
        }
        return
      }

      task?.onOpen?.(() => {
        reconnectAttempt = 0
        notifyConnected(true)
        // 30s 心跳
        if (heartbeatTimer) clearInterval(heartbeatTimer)
        heartbeatTimer = setInterval(() => {
          try {
            sharedSocketTask?.then((t) => t?.send?.({ data: JSON.stringify({ event: 'ping' }) }))
          } catch {
            // 心跳发送失败忽略，由 onClose 触发重连
          }
        }, HEARTBEAT_INTERVAL)
        // 重连后拉取断连期间消息
        sharedListeners.forEach((l) => l.onReconnect?.())
      })

      task?.onMessage?.((res: any) => {
        let msg: WsMessage
        try {
          msg = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
        } catch {
          msg = { raw: res.data }
        }
        // API §14.2：pong 返回 token_expired=true 时刷新 Token 并重建连接
        if (msg.event === 'pong') {
          if (msg.data?.token_expired) {
            useAuthStore
              .getState()
              .refreshAccessToken()
              .then((ok) => {
                if (!ok) return // 刷新失败：401 拦截器负责跳登录
                closeShared(false)
                reconnectAttempt = 0
                connectShared()
              })
          }
          return
        }
        // 内置通知域事件（connected/notification/sync/export_completed）单次消化
        if (handleBuiltinEvent(msg)) return
        // 领域事件分发（badge_unlocked/payment_success/analysis_*/score_update 等）
        sharedListeners.forEach((l) => l.onMessage?.(msg))
      })

      task?.onClose?.(() => {
        notifyConnected(false)
        cleanupHeartbeat()
        if (isManualClose) return
        scheduleReconnect()
      })

      task?.onError?.(() => {
        notifyConnected(false)
        cleanupHeartbeat()
      })
    })
    .catch(() => {
      notifyConnected(false)
      cleanupHeartbeat()
      scheduleReconnect()
    })
}

/** 关闭共享连接（manual=true 表示最后一个消费者卸载） */
function closeShared(manual: boolean) {
  isManualClose = manual
  if (pendingReconnectTimer) {
    clearTimeout(pendingReconnectTimer)
    pendingReconnectTimer = null
  }
  cleanupHeartbeat()
  const taskPromise = sharedSocketTask
  sharedSocketTask = null
  taskPromise?.then((task) => {
    try {
      task?.close?.({})
    } catch {
      // 任务可能尚未建立，忽略
    }
  })
  if (manual) {
    reconnectAttempt = 0
    notifyConnected(false)
  }
}

/**
 * WebSocket 连接管理 Hook（共享单例）。
 * 首个消费者挂载建立连接；最后一个卸载关闭连接；
 * 每个 Hook 的 onMessage/onReconnect 以引用计数监听器形式分发。
 */
export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const [connected, setConnected] = useState(sharedConnected)
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    if (url === null) return
    const listener: Listener = {
      get onMessage() {
        return optionsRef.current.onMessage
      },
      get onReconnect() {
        return optionsRef.current.onReconnect
      },
    }
    const onConnectedChange = (v: boolean) => setConnected(v)
    connectedSubscribers.add(onConnectedChange)
    sharedListeners.add(listener)
    connectionCount++
    if (connectionCount === 1) {
      reconnectAttempt = 0
      connectShared()
    } else if (!sharedConnected && !sharedSocketTask) {
      // 已有消费者但连接缺失（如 Token 刷新窗口）：恢复
      connectShared()
    }

    return () => {
      sharedListeners.delete(listener)
      connectedSubscribers.delete(onConnectedChange)
      connectionCount--
      if (connectionCount === 0) {
        closeShared(true)
      }
    }
    // url 变化重建监听（设计允许静态 URL，此处仅做挂载/卸载计数）
  }, [url])

  /** 手动发送消息（经共享连接） */
  const send = useCallback((data: WsMessage) => {
    sharedSocketTask?.then((task) => {
      try {
        task?.send?.({ data: JSON.stringify(data) })
      } catch {
        // 发送失败忽略
      }
    })
  }, [])

  return { connected, socketTask: sharedSocketTask, send }
}

export default useWebSocket
