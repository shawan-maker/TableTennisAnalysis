/**
 * gamification 常量（09-gamification/frontend.md §7 L925-945）
 * R-FE-R2 批次E（FE-P3-19）：设计承诺本文件（POINTS_SOURCE_MAP /
 * BADGE_CATEGORY_MAP），修复前零命中、对应 10 个 i18n 键为死键。
 * 原注记「消费端接线归批次 G 跨栈协调」失实——批次G 交付清单不含此项
 * （R2-P2-1 判定），已在本批次H 完成：
 * - BADGE_CATEGORY_MAP：badges 页分类标签消费（后端 BadgeEarned/BadgeLocked
 *   schema 已补 category 透出，R2-P2-1）；
 * - POINTS_SOURCE_MAP：积分历史端点（GET /gamification/points-history，
 *   R2-P2-2 后端补 PointTransaction 流水表 + 端点，前端 PointsCard 最近
 *   动态区消费——home + checkin-calendar 两页挂载，R2-P3-1 注记修正：
 *   项目无独立 history 页，原注记「history 页消费」失实）。
 */

/** 积分来源标签映射 */
export const POINTS_SOURCE_MAP: Record<string, string> = {
  analysis: 'gamification.sourceAnalysis',
  match: 'gamification.sourceMatch',
  record: 'gamification.sourceRecord',
  checkin: 'gamification.sourceCheckin',
  streak_7: 'gamification.sourceStreak7',
  streak_30: 'gamification.sourceStreak30',
}

/** 徽章分类映射 */
export const BADGE_CATEGORY_MAP: Record<string, string> = {
  analysis: 'gamification.categoryAnalysis',
  match: 'gamification.categoryMatch',
  streak: 'gamification.categoryStreak',
  general: 'gamification.categoryGeneral',
}
