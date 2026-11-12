/**
 * scoring 常量（04-scoring/frontend.md §7）
 * - labelKey 统一走 i18n（P1-FE3），禁止硬编码文本
 * - match_data 模块复用本文件常量（05-match_data/frontend.md §7）
 */

/** 赛制选项 */
export interface FormatOption {
  value: 'bo1' | 'bo3' | 'bo5' | 'bo7' | 'custom'
  labelKey: string
}

export const FORMAT_OPTIONS: FormatOption[] = [
  { value: 'bo1', labelKey: 'scoring.format_bo1' },
  { value: 'bo3', labelKey: 'scoring.format_bo3' },
  { value: 'bo5', labelKey: 'scoring.format_bo5' },
  { value: 'bo7', labelKey: 'scoring.format_bo7' },
  { value: 'custom', labelKey: 'scoring.format_custom' },
]

/** 比赛类型选项 */
export interface MatchTypeOption {
  value: 'friendly' | 'tournament' | 'training'
  labelKey: string
}

export const MATCH_TYPE_OPTIONS: MatchTypeOption[] = [
  { value: 'friendly', labelKey: 'scoring.matchType_friendly' },
  { value: 'tournament', labelKey: 'scoring.matchType_tournament' },
  { value: 'training', labelKey: 'scoring.matchType_training' },
]

/**
 * 得分方式（记分时快速选择）
 * - technique 为 undefined 时表示不标记技术动作
 * - 后端 ScoreRequest.technique_action 为可选字符串（max_length=30）
 */
export interface ScoreMethodOption {
  value: 'serve_point' | 'rally_point' | 'opponent_error'
  labelKey: string
  technique?: string
}

export const SCORE_METHODS: ScoreMethodOption[] = [
  { value: 'serve_point', labelKey: 'scoring.method.serve_point' },
  { value: 'rally_point', labelKey: 'scoring.method.rally_point' },
  { value: 'opponent_error', labelKey: 'scoring.method.opponent_error' },
  { value: 'rally_point', labelKey: 'scoring.method.forehand_drive', technique: 'forehand_drive' },
  { value: 'rally_point', labelKey: 'scoring.method.backhand_drive', technique: 'backhand_drive' },
  { value: 'rally_point', labelKey: 'scoring.method.forehand_loop', technique: 'forehand_loop' },
]

/**
 * 每局目标分选项（R-FE-R1 批次C FE-P2-13：04-scoring v1.0 L478 承诺 21 分制；
 * 后端契约 target_score 1-21，11/21 为需求承诺的预设切换项）
 */
export interface TargetScoreOption {
  value: 11 | 21
  labelKey: string
}

export const TARGET_SCORE_OPTIONS: TargetScoreOption[] = [
  { value: 11, labelKey: 'scoring.targetScore11' },
  { value: 21, labelKey: 'scoring.targetScore21' },
]

/** 比赛状态映射（列表筛选 + 状态标签） */
export interface MatchStatusMeta {
  labelKey: string
  /** 对应 CSS 变量名后缀（status-${color} 样式类） */
  color: string
}

export const MATCH_STATUS_MAP: Record<string, MatchStatusMeta> = {
  all: { labelKey: 'scoring.status.all', color: '' },
  setup: { labelKey: 'scoring.status.setup', color: 'accent' },
  in_progress: { labelKey: 'scoring.status.in_progress', color: 'success' },
  finished: { labelKey: 'scoring.status.finished', color: 'secondary' },
  abandoned: { labelKey: 'scoring.status.abandoned', color: 'divider' },
}
