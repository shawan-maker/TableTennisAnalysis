/**
 * E2E-05 通知交互 mock 状态机（docs/07实施计划/02-测试计划.md §7.5 / FS8-6）
 *
 * 以内存状态镜像后端语义（响应字段与 services/notification.ts 镜像的后端 schema 逐字一致）：
 * - GET  /notification/list?page&page_size&is_read   三态筛选（unread→is_read=false /
 *   read→is_read=true / all→无参数；后端 notification_service list 过滤语义）
 * - POST /notification/read {notification_ids}        批量标记已读（1-100 条，API §13.2）
 *   → state.readIds 翻转 + updated_count 回传
 * - GET  /notification/unread-count                  未读数随 readIds 派生
 *   （export_completed WS → fetchUnreadCount 幂等角标刷新的断言锚点）
 *
 * WS 直推 notification 事件（useWebSocket.handleBuiltinEvent 合成负时间戳 id 头插、
 * unreadCount 本地 +1）不入 mock 状态——升级后的未读数在本地 store（后端在线直推
 * 不落库，12-notification/frontend.md §4）。
 */
import type { MockRoute } from './mock-api'

const iso = () => new Date().toISOString()

/** 通知条目（NotificationItem 镜像） */
export interface NotifState {
  id: number
  type: string
  title: string
  content: string | null
  is_read: boolean
  extra_data: Record<string, unknown> | null
  created_at: string
}

export function createNotificationMocks() {
  const items: NotifState[] = [
    {
      id: 5001,
      type: 'analysis_complete',
      title: '分析报告已生成',
      content: '你的分析报告 #7 已生成，点击查看详情',
      is_read: false,
      extra_data: null, // 无 action_url：点击仅标记已读不跳转（E2E 断言停留在列表页）
      created_at: iso(),
    },
    {
      id: 5002,
      type: 'badge_unlocked',
      title: '徽章解锁：训练达人',
      content: '连续训练 7 天达成，徽章已发放',
      is_read: false,
      extra_data: null,
      created_at: iso(),
    },
    {
      id: 5003,
      type: 'score_update',
      title: '比赛比分已更新',
      content: '比赛 #12 的比分记录已同步',
      is_read: true,
      extra_data: null,
      created_at: iso(),
    },
  ]
  /** 已标记已读的 id（POST /notification/read 翻转） */
  const state: { readIds: Set<number> } = { readIds: new Set() }

  const routes: MockRoute[] = [
    // 通知列表（API §13.1，is_read 三态筛选）
    {
      method: 'GET',
      pattern: '/notification/list',
      dynamic: ({ query }) => {
        const isReadParam = query.get('is_read')
        const filtered = items.filter((n) => {
          const effRead = n.is_read || state.readIds.has(n.id)
          if (isReadParam === null) return true
          return isReadParam === 'true' ? effRead : !effRead
        })
        return {
          total: filtered.length,
          page: 1,
          page_size: 20,
          items: filtered.map((n) => ({
            ...n,
            is_read: n.is_read || state.readIds.has(n.id),
          })),
        }
      },
    },
    // 批量标记已读（API §13.2）
    {
      method: 'POST',
      pattern: '/notification/read',
      dynamic: ({ body }) => {
        const ids: number[] = Array.isArray(body?.notification_ids) ? body.notification_ids : []
        let updated = 0
        for (const id of ids) {
          if (!state.readIds.has(id)) {
            state.readIds.add(id)
            updated++
          }
        }
        return { updated_count: updated }
      },
    },
    // 未读数（API §13.4；随 readIds 派生）
    {
      method: 'GET',
      pattern: '/notification/unread-count',
      dynamic: () => ({
        unread_count: items.filter((n) => !n.is_read && !state.readIds.has(n.id)).length,
      }),
    },
  ]

  return { routes, state }
}
