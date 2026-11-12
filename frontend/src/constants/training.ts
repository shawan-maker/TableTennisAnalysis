/**
 * training 常量（07-training_advice/frontend.md §7 L1870-1904）
 * R-FE-R1 批次C（FE-P3-17）：SEVERITY/TREND/SUGGESTION_TYPE/ADJUSTMENT_ACTION
 * 四映射修复前内联在 DiagnosisSection/SuggestionSection 组件（且
 * ADJUSTMENT_ACTION_MAP 全仓零命中），按设计收敛至本文件；labelKey 走 i18n。
 */

export interface StyleMeta {
  icon?: string
  color: string
  labelKey: string
}

/** 严重程度映射（§7 SEVERITY_MAP：低=绿 / 中=橙 / 高=红；嵌套键 training.severity.*） */
export const SEVERITY_MAP: Record<string, StyleMeta> = {
  low: { color: 'var(--color-success)', labelKey: 'training.severity.low' },
  medium: { color: 'var(--color-accent)', labelKey: 'training.severity.medium' },
  high: { color: 'var(--color-primary)', labelKey: 'training.severity.high' },
}

/** 趋势映射（§7 TREND_MAP） */
export const TREND_MAP: Record<string, StyleMeta> = {
  improving: { icon: '↑', color: 'var(--color-success)', labelKey: 'training.trendImproving' },
  stagnant: { icon: '→', color: 'var(--color-accent)', labelKey: 'training.trendStagnant' },
  declining: { icon: '↓', color: 'var(--color-primary)', labelKey: 'training.trendDeclining' },
  achieved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendAchieved' },
  new: { icon: '★', color: 'var(--color-accent)', labelKey: 'training.trendNew' },
  resolved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendResolved' },
}

/** 建议类型映射（§7 SUGGESTION_TYPE_MAP） */
export const SUGGESTION_TYPE_MAP: Record<string, StyleMeta> = {
  progress_confirm: { icon: '✅', color: 'var(--color-success)', labelKey: 'training.progressConfirm' },
  persistent_warning: { icon: '⚠️', color: 'var(--color-accent)', labelKey: 'training.persistentWarning' },
  new_issue: { icon: '🔴', color: 'var(--color-primary)', labelKey: 'training.newIssue' },
  first_analysis: { icon: 'ℹ️', color: 'var(--color-secondary)', labelKey: 'training.firstAnalysis' },
}

/**
 * 方案调整动作映射（§7 ADJUSTMENT_ACTION_MAP，修复前全仓零命中）。
 * 注记：设计 §7 样例此表 labelKey 复用 TREND 键系（improving/stagnant/declining/
 * achieved，文档复制痕迹，语义不通——「维持」不会是「改善中」），按动作语义
 * 新增专用键 training.action*（R-FE-R1 偏差注记）。
 */
export const ADJUSTMENT_ACTION_MAP: Record<string, StyleMeta> = {
  maintain: { color: 'var(--color-success)', labelKey: 'training.actionMaintain' },
  adjust: { color: 'var(--color-accent)', labelKey: 'training.actionAdjust' },
  escalate: { color: 'var(--color-primary)', labelKey: 'training.actionEscalate' },
  new_goal: { color: 'var(--color-secondary)', labelKey: 'training.actionNewGoal' },
}
