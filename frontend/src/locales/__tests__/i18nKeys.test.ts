/**
 * i18n 双语言 key 完整性测试（04-前端实施计划.md §6.2 双语言层：零缺失 key）
 * zh-CN 与 en-US 的扁平 key 集合必须完全一致（CI 门控：key diff 校验）
 */
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

/** 递归展平嵌套对象为点号 key 集合 */
function flattenKeys(obj: Record<string, any>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return flattenKeys(value, path)
    }
    return [path]
  })
}

describe('i18n 双语言 key 完整性（zh-CN vs en-US）', () => {
  const zhKeys = flattenKeys(zhCN).sort()
  const enKeys = flattenKeys(enUS).sort()

  it('zh-CN 与 en-US key 集合完全一致（零缺失）', () => {
    const onlyInZh = zhKeys.filter((k) => !enKeys.includes(k))
    const onlyInEn = enKeys.filter((k) => !zhKeys.includes(k))
    expect(onlyInZh).toEqual([])
    expect(onlyInEn).toEqual([])
  })

  it('所有 key 的值为非空字符串', () => {
    const emptyZh = zhKeys.filter((k) => {
      const val = k.split('.').reduce<any>((acc, seg) => acc?.[seg], zhCN)
      return typeof val !== 'string' || val.trim() === ''
    })
    const emptyEn = enKeys.filter((k) => {
      const val = k.split('.').reduce<any>((acc, seg) => acc?.[seg], enUS)
      return typeof val !== 'string' || val.trim() === ''
    })
    expect(emptyZh).toEqual([])
    expect(emptyEn).toEqual([])
  })
})

describe('FS2 域 key 存在性（scoring.* / matchData.*）', () => {
  const scoringZh = zhCN.scoring as Record<string, any>

  it('scoring 域核心 key 齐备（设置页/记分页/统计页/列表页/常量）', () => {
    const expected = [
      'matchSetup', 'startMatch', 'createFailed', 'fillOpponentName',
      'iScored', 'opponentScored', 'undo', 'finishMatch', 'selectMethod',
      'youWin', 'youLose', 'scoreDistribution', 'techniqueBreakdown',
      'keyPoints', 'totalPoints', 'newMatch', 'noMatches', 'wsDisconnected',
      'format_bo1', 'format_bo3', 'format_bo5', 'format_bo7', 'format_custom',
      'matchType_friendly', 'matchType_tournament', 'matchType_training',
    ]
    const missing = expected.filter((k) => !(k in scoringZh))
    expect(missing).toEqual([])
  })

  it('scoring.method.* 覆盖 SCORE_METHODS 全部 6 个 labelKey', () => {
    const method = scoringZh.method
    expect(Object.keys(method)).toEqual(
      expect.arrayContaining([
        'serve_point', 'rally_point', 'opponent_error',
        'forehand_drive', 'backhand_drive', 'forehand_loop',
      ])
    )
  })

  it('scoring.status.* 覆盖 MATCH_STATUS_MAP 全部 5 个状态', () => {
    const status = scoringZh.status
    expect(Object.keys(status)).toEqual(
      expect.arrayContaining(['all', 'setup', 'in_progress', 'finished', 'abandoned', 'unknown'])
    )
  })

  it('matchData 域核心 key 齐备（快速/详细录入/列表/详情）', () => {
    const matchDataZh = zhCN.matchData as Record<string, any>
    const expected = [
      'quickEntry', 'quickEntryDesc', 'detailedEntry', 'detailedEntryDesc',
      'myScore', 'oppScore', 'scoreCannotBeEqual', 'submit', 'switchToDetailed',
      'scoreDetails', 'needAtLeastOneDetail', 'currentScore',
      'recordWin', 'recordLose', 'newRecord', 'noRecords', 'matchDate',
    ]
    const missing = expected.filter((k) => !(k in matchDataZh))
    expect(missing).toEqual([])
    expect(Object.keys(matchDataZh.filter)).toEqual(['all', 'win', 'lose'])
  })

  it('common.loadMore / common.delete 存在（列表分页与左滑删除用）', () => {
    expect((zhCN.common as Record<string, string>).loadMore).toBeTruthy()
    expect((zhCN.common as Record<string, string>).delete).toBeTruthy()
    expect((enUS.common as Record<string, string>).loadMore).toBeTruthy()
    expect((enUS.common as Record<string, string>).delete).toBeTruthy()
  })
})
