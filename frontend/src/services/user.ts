/**
 * user 模块 API Service（02-user/frontend.md §2）
 * 端点与后端 app/api/v1/users/router.py 逐字一致
 */
import request from './request'

/**
 * 获取个人档案。
 * 返回用户基础信息 + profile（含 kqs_rating, playing_style, equipment_config, profile_completeness）
 */
export function getProfile() {
  return request.get('/users/profile')
}

/**
 * 更新个人档案（PATCH 语义，仅更新传入字段）。
 * @param data - playing_style / self_assessed_level / equipment_config
 */
export function updateProfile(data: {
  playing_style?: string
  self_assessed_level?: string
  equipment_config?: Record<string, any>
}) {
  return request.patch('/users/profile', data)
}

/**
 * 更新开球网积分。
 * @param rating - 积分值 (500-3000)
 * @param kqsUsername - 开球网用户名（可选）
 * @param source - 来源: manual / kqs_sync
 */
export function updateRating(rating: number, kqsUsername?: string, source: string = 'manual') {
  return request.patch('/users/rating', { rating, kqs_username: kqsUsername, source })
}

/**
 * 积分历史记录（分页）。
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getRatingHistory(page: number = 1, pageSize: number = 20) {
  return request.get('/users/rating-history', { page, page_size: pageSize })
}

/**
 * 免费分析额度状态（R6-User-2：端点未记录于 API §3，代码实现先行）。
 * 返回 { daily_limit, used_today, remaining, reset_at, bonus_remaining }。
 * bonus_remaining（R15-VA-N1）：付费分析包剩余额度，免费日额度耗尽后回退消耗该池，
 * 展示层须如实反映，否则购包用户看到 remaining=0 误判无法使用。
 */
export function getQuota() {
  return request.get('/users/quota')
}

/**
 * 乒乓大数据（趣味统计，24h 缓存）。
 */
export function getBigData() {
  return request.get('/users/big-data')
}

/**
 * 用户注销（72h 冷静期）。
 * @param reason - 注销原因
 * @param confirmation - 必须为 "DELETE_ACCOUNT_CONFIRM"
 */
export function deleteAccount(reason: string, confirmation: string) {
  return request.delete('/users/account', { reason, confirmation })
}

/**
 * 取消注销（冷静期内可撤销）。
 */
export function cancelDeletion() {
  return request.post('/users/account/cancel-deletion')
}

/**
 * 发起个人数据导出（PIPL 数据可携带权）。
 */
export function exportData() {
  return request.post('/users/export-data')
}

/**
 * 查询导出状态 + 下载链接。
 * @param taskId - 导出任务 ID
 */
export function getExportStatus(taskId: string) {
  return request.get(`/users/export-data/${taskId}`)
}
