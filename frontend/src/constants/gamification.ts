/**
 * gamification 常量（09-gamification/frontend.md §7 L925-945）
 * R-FE-R2 批次E（FE-P3-19）：设计承诺本文件（POINTS_SOURCE_MAP /
 * BADGE_CATEGORY_MAP），修复前零命中、对应 10 个 i18n 键为死键。
 * 补建后常量层就绪——消费端接线（badges 页分类标签 / 积分历史来源行）
 * 依赖后端 schema 暴露 category/source 字段，归批次 G 跨栈协调。
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
