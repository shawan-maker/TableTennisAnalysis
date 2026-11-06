/**
 * notification 模块 API Service（12-notification/frontend.md §2）
 * 端点与后端 app/api/v1/notification/router.py 逐字一致（4 个）。
 */
import request from './request'

/** 通知条目（app/schemas/notification.py NotificationBrief） */
export interface NotificationItem {
  id: number
  type: string
  title: string
  content: string | null
  is_read: boolean
  extra_data: Record<string, any> | null
  created_at: string
}

/** 通知列表查询参数 */
export interface NotificationListParams {
  is_read?: boolean
  type?: string
  page?: number
  page_size?: number
}

/** 通知列表响应（Paginated 包装） */
export interface NotificationListData {
  total: number
  page: number
  page_size: number
  items: NotificationItem[]
}

/** 标记已读响应 */
export interface MarkReadData {
  updated_count: number
}

/** 订阅授权响应 */
export interface SubscribeData {
  subscribed_templates: string[]
}

/** 未读数量响应 */
export interface UnreadCountData {
  unread_count: number
}

/**
 * 获取通知列表（分页，API §13.1）。
 * @param params - 查询参数（page/page_size 缺省 1/20，page_size 上限 50）
 */
export function listNotifications(params: NotificationListParams = {}) {
  return request.get<NotificationListData>('/notification/list', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 批量标记已读（API §13.2，1-100 条）。
 * @param notification_ids - 通知 ID 列表
 */
export function markRead(notification_ids: number[]) {
  return request.post<MarkReadData>('/notification/read', { notification_ids })
}

/**
 * 微信订阅消息授权（API §13.3）。
 * @param template_ids - 模板 ID 列表
 */
export function subscribeTemplates(template_ids: string[]) {
  return request.post<SubscribeData>('/notification/subscribe', { template_ids })
}

/**
 * 获取未读通知数量（API §13.4）。
 */
export function getUnreadCount() {
  return request.get<UnreadCountData>('/notification/unread-count')
}
