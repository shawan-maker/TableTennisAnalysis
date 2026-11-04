/**
 * useWebSocket — 统一 WebSocket Hook（总览 §3.3/§3.6）
 *
 * - 连接地址：buildWsUrl(token)（wss://api.pingpongai.com/ws?token=xxx，开发环境 ws://localhost:8000/ws）
 * - 指数退避重连：1 → 2 → 4 → 8 → 16s，最大 5 次（禁止固定间隔）
 * - 30s 心跳 ping 维持连接活性
 * - 重连成功后回调 onReconnect() 拉取断连期间错过的消息
 *
 * weapp 端无全局 WebSocket，使用 Taro.connectSocket（SocketTask）屏蔽端差异；
 * H5 端 Taro.connectSocket 同样返回 Promise<SocketTask>，行为一致。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'

const RECONNECT_DELAYS = [1, 2, 4, 8, 16] // 秒，指数退避

export interface WsMessage {
  event?: string
  [key: string]: any
}

export interface UseWebSocketOptions {
  /** 收到消息（已尝试 JSON 解析） */
  onMessage?: (msg: WsMessage) => void
  /** 连接/重连成功后回调（拉取断连期间消息） */
  onReconnect?: () => void
}

/** 构造 WS 连接地址 */
export function buildWsUrl(token: string): string {
  const base = process.env.TARO_APP_WS || 'wss://api.pingpongai.com/ws'
  return `${base}?token=${token}`
}

export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const [connected, setConnected] = useState(false)
  const socketTaskRef = useRef<Promise<any> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const manualCloseRef = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options
  const urlRef = useRef(url)
  urlRef.current = url

  const cleanupHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current)
      heartbeatRef.current = null
    }
  }, [])

  /** 指数退避重连: 1→2→4→8→16s，最大 5 次 */
  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptRef.current >= RECONNECT_DELAYS.length) return
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)]
    reconnectAttemptRef.current++
    setTimeout(() => connectRef.current(), delay * 1000)
  }, [])

  const connect = useCallback(() => {
    const url = urlRef.current
    if (!url) return
    manualCloseRef.current = false
    // Taro.connectSocket 返回 Promise<SocketTask>（weapp/H5 行为一致）
    const taskPromise: Promise<any> = Taro.connectSocket({ url })
    socketTaskRef.current = taskPromise

    taskPromise
      .then((task) => {
        // 等待期间组件已卸载：立即关闭连接
        if (manualCloseRef.current) {
          try {
            task.close({})
          } catch {
            // 忽略
          }
          return
        }

        task.onOpen(() => {
          setConnected(true)
          reconnectAttemptRef.current = 0
          // 30s 心跳
          heartbeatRef.current = setInterval(() => {
            try {
              socketTaskRef.current?.then((t) => t?.send({ data: JSON.stringify({ event: 'ping' }) }))
            } catch {
              // 心跳发送失败忽略，由 onClose 触发重连
            }
          }, 30000)
          // 重连后拉取断连期间消息
          optionsRef.current.onReconnect?.()
        })

        task.onMessage((res) => {
          let msg: WsMessage
          try {
            msg = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
          } catch {
            msg = { raw: res.data }
          }
          optionsRef.current.onMessage?.(msg)
        })

        task.onClose(() => {
          setConnected(false)
          cleanupHeartbeat()
          if (manualCloseRef.current) return
          scheduleReconnect()
        })

        task.onError(() => {
          setConnected(false)
          cleanupHeartbeat()
        })
      })
      .catch(() => {
        // 连接建立失败：同样进入退避重连
        setConnected(false)
        cleanupHeartbeat()
        scheduleReconnect()
      })
  }, [cleanupHeartbeat, scheduleReconnect])

  // connect 自引用（供 scheduleReconnect 回调）
  const connectRef = useRef(connect)
  connectRef.current = connect

  useEffect(() => {
    connectRef.current()
    return () => {
      manualCloseRef.current = true
      cleanupHeartbeat()
      socketTaskRef.current?.then((task) => {
        try {
          task?.close({})
        } catch {
          // 任务可能尚未建立，忽略
        }
      })
    }
  }, [cleanupHeartbeat])

  /** 手动发送消息 */
  const send = useCallback((data: WsMessage) => {
    socketTaskRef.current?.then((task) => {
      try {
        task?.send({ data: JSON.stringify(data) })
      } catch {
        // 发送失败忽略
      }
    })
  }, [])

  return { connected, socketTask: socketTaskRef.current, send }
}

export default useWebSocket
