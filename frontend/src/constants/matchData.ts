/**
 * match_data 常量（05-match_data/frontend.md §1326「前端拦截 + 后端校验」双层）
 *
 * R-FE-R1 批次B（FE-P1-14）：局分语义前端预校验——后端 _validate_score_by_format
 * 对 bo 系列要求 my_score/opponent_score 为局分（bo5 → 3:1），逐分累计式总分
 * 必被 422 拒收；修复前前端零拦截仅 Toast err.message 无引导。
 * 本文件逐字镜像 app/services/match_data_service.py 的 FORMAT_WIN_MAP 与判定逻辑。
 */

/** 赛制 → 赢方所需局数（镜像后端 MatchDataService.FORMAT_WIN_MAP） */
export const FORMAT_WIN_MAP: Record<string, number> = {
  bo1: 1,
  bo3: 2,
  bo5: 3,
  bo7: 4,
}

/**
 * 比分是否符合赛制规则（镜像后端 _validate_score_by_format）：
 * - custom：仅要求双方不等
 * - bo 系列：赢方必须恰好 == win_needed、输方 < win_needed（局分语义）
 */
export function validateScoreByFormat(myScore: number, oppScore: number, fmt: string): boolean {
  if (fmt === 'custom') return myScore !== oppScore
  const winNeeded = FORMAT_WIN_MAP[fmt]
  if (winNeeded === undefined) return false
  if (myScore === winNeeded) return oppScore < winNeeded
  if (oppScore === winNeeded) return myScore < winNeeded
  return false
}
