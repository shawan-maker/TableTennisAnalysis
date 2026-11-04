/**
 * useMatchSync — 记分牌 WebSocket 订阅 Hook（04-scoring/frontend.md §8）
 *
 * 订阅比赛频道实时更新比分，用于多设备同步：设备 A 记分，设备 B 自动收到更新。
 *
 * FS2-P3 契约同步（实现以后端 ws.py receive_loop 为准，设计样例
 * `{event:'join', room:'ws:match:{id}'}` 为 v0 假想协议，后端实际协议为
 * `{event:'subscribe', match_id:<int>}`，订阅成功后服务端自动推 `subscribed`
 * ack + `sync_match` 全量同步（R12-SC-2，断连重连补偿由该链路承担））。
 */
import { useEffect } from 'react'
import { useScoringStore } from '@/stores/scoringStore'
import { useWebSocket, buildWsUrl } from '@/hooks/useWebSocket'
import type { WsMessage } from '@/hooks/useWebSocket'

/** 本 Hook 消费的比赛事件（API §14.2） */
export const MATCH_WS_EVENTS = ['score_update', 'sync_match', 'match_finished'] as const

/** 构造订阅消息体（后端 ws.py receive_loop 协议） */
export function buildSubscribeMessage(matchId: number): WsMessage {
  return { event: 'subscribe', match_id: matchId }
}

/**
 * 判断消息是否属于当前比赛（两级分发：先按 event 再按 match_id）。
 * - score_update / sync_match 携带 match_id，需匹配
 * - match_finished 走用户频道（后端 push_ws_message）广播，payload 亦携带
 *   match_id：有值时按其过滤（防止其他比赛的结束事件误触发本页跳转），
 *   缺省时按事件名兜底
 * - connected / subscribed / pong 为连接控制消息，不属于业务事件
 */
export function isMatchWsEvent(msg: WsMessage, matchId: number): boolean {
  if (!msg?.event) return false
  if (msg.event === 'connected' || msg.event === 'subscribed' || msg.event === 'pong') return false
  const data = msg.data
  if (data && typeof data === 'object' && data.match_id !== undefined) {
    return data.match_id === matchId
  }
  return (MATCH_WS_EVENTS as readonly string[]).includes(msg.event)
}

/**
 * 订阅比赛 WebSocket 推送，实时更新比分。
 * @param matchId - 比赛 ID，null 时不建立连接
 * @returns isConnected - WebSocket 连接状态（断线横幅用）
 */
export function useMatchSync(matchId: number | null) {
  const fetchMatch = useScoringStore((s) => s.fetchMatch)
  const applyWsScoreUpdate = useScoringStore((s) => s.applyWsScoreUpdate)

  const { connected: isConnected, send } = useWebSocket(matchId != null ? buildWsUrl() : null, {
    onMessage: (msg) => {
      if (matchId == null || !isMatchWsEvent(msg, matchId)) return
      if (msg.event === 'score_update') {
        // 乐观更新（多设备即时刷新），随后 fetchMatch 对账
        // 双路径处理：eventCenter 广播给跨模块订阅者，此处负责即时刷新比分页
        applyWsScoreUpdate(matchId, msg.data || {})
        fetchMatch(matchId)
      } else {
        // sync_match（订阅/重连后全量同步）/ match_finished（结束通知）→ 重新拉详情
        fetchMatch(matchId)
      }
    },
    // 断连重连补偿：onOpen 后 connected effect 重新 send subscribe，
    // 服务端订阅 ack 后自动推 sync_match 全量同步（R12-SC-2），无需在此重复拉取
  })

  // 连接就绪后加入比赛房间（后端 subscribe 协议）
  useEffect(() => {
    if (matchId == null || !isConnected) return
    send(buildSubscribeMessage(matchId))
  }, [matchId, isConnected, send])

  return { isConnected }
}

export default useMatchSync
