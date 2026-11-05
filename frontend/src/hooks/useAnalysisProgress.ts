/**
 * useAnalysisProgress — 分析进度 WebSocket Hook（03-video_analysis/frontend.md §8）
 *
 * 实时推送 analysis_progress / analysis_complete / analysis_failed + REST 轮询兜底。
 *
 * FS3-P3 契约修正（以后端为准，与设计样例的差异）：
 * 1. taskId 为 number（router 路径参数 task_id: int；设计样例 string 为 v0 口径）
 * 2. WS 认证走 Sec-WebSocket-Protocol: jwt.{token} 子协议（API §14.1），
 *    设计样例的 ?token= URL 查询参数为 v0 形态（FS2 已全站修正）
 * 3. 无需 subscribe：analysis_* 事件经用户频道 ws:user:{uid} 广播，后端 ws.py
 *    连接建立时即订阅用户频道（receive_loop 仅支持 subscribe+match_id，设计样例
 *    的 {event:'subscribe', channel:'task:{id}'} 为假想协议，后端不解析）
 * 4. analysis_progress payload.progress 为 0.0-1.0 浮点（后端 ProgressTracker._calc_progress），
 *    设计注记 R18-P3-17 所写 0~100 为口径偏差；onProgress 对外统一 0-100 百分比
 * 5. 轮询兜底按 R18-P3-17 结论补齐 getTaskDetail 调用（每 5s 对账）
 * 6. 重连由统一 useWebSocket 管理（指数退避 1→16s + 30s 心跳），不单独透出 retryCount
 */
import { useEffect } from 'react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import type { WsMessage } from '@/hooks/useWebSocket'

/** 本 Hook 消费的分析事件（后端 app/ai_pipeline/progress.py push_ws_message） */
export const ANALYSIS_WS_EVENTS = ['analysis_progress', 'analysis_complete', 'analysis_failed'] as const

/**
 * 判断消息是否属于当前任务（事件名 + payload.task_id 双匹配）。
 * analysis_* 均走用户频道广播且恒携带 task_id，不匹配的任务事件须丢弃
 * （防止页面 A 任务的进度被页面 B 的任务事件误刷新）。
 */
export function isAnalysisWsEvent(msg: WsMessage, taskId: number): boolean {
  if (!msg?.event) return false
  if (!(ANALYSIS_WS_EVENTS as readonly string[]).includes(msg.event)) return false
  const data = msg.data
  return !!(data && typeof data === 'object' && data.task_id === taskId)
}

interface UseAnalysisProgressOptions {
  taskId: number
  /** 分析完成（report_id 就绪） */
  onComplete?: (reportId: number) => void
  /** 进度更新（0-100 百分比） */
  onProgress?: (progress: number) => void
}

/**
 * 订阅分析任务进度。
 * @returns connected - WebSocket 实时连接状态（断开时轮询兜底仍然生效）
 */
export function useAnalysisProgress({ taskId, onComplete, onProgress }: UseAnalysisProgressOptions) {
  const fetchTaskDetail = useVideoAnalysisStore((s) => s.fetchTaskDetail)
  const applyWsProgress = useVideoAnalysisStore((s) => s.applyWsProgress)

  // WS 实时推送（统一 useWebSocket：子协议认证 + 指数退避重连 + 心跳）；
  // taskId 非法时不建立连接（仅轮询兜底）
  const { connected } = useWebSocket(taskId > 0 ? buildWsUrl() : null, {
    onMessage: (msg) => {
      if (taskId <= 0 || !isAnalysisWsEvent(msg, taskId)) return
      const data = msg.data || {}
      if (msg.event === 'analysis_progress') {
        // 后端 progress 0.0-1.0 → 乐观更新 + 对外 0-100 百分比
        const pct = Math.round(Math.min(1, Math.max(0, data.progress ?? 0)) * 100)
        applyWsProgress(taskId, data.progress ?? 0)
        onProgress?.(pct)
      } else if (msg.event === 'analysis_complete') {
        // 完成态以 fetchTaskDetail 对账为准（status=completed + report_id）
        fetchTaskDetail(taskId)
        if (typeof data.report_id === 'number') onComplete?.(data.report_id)
      } else if (msg.event === 'analysis_failed') {
        // 失败态对账（页面自动进入失败分支）
        fetchTaskDetail(taskId)
      }
    },
  })

  // 初始加载 + REST 轮询兜底（每 5s 对账；WS 断线/丢包时仍可推进进度条）
  useEffect(() => {
    if (taskId <= 0) return
    fetchTaskDetail(taskId)
    const timer = setInterval(() => {
      fetchTaskDetail(taskId)
    }, 5000)
    return () => clearInterval(timer)
  }, [taskId, fetchTaskDetail])

  return { connected }
}

export default useAnalysisProgress
