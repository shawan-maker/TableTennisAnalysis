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

  it('analysis 域核心 key 齐备（上传引导/进度/报告/反馈/分享，FS3）', () => {
    const analysisZh = zhCN.analysis as Record<string, any>
    const expected = [
      'shootingGuide', 'noticeFormat', 'freeQuotaHint', 'chooseVideo',
      'uploading', 'uploadFailed', 'taskCreated', 'analyzing',
      'estimatedRemaining', 'analysisComplete', 'viewReport', 'analysisFailed',
      'totalRallies', 'landingDistribution', 'landingHint', 'techniqueDistribution',
      'ballSpeed', 'conclusion', 'videoPlayback', 'feedbackPrompt',
      'shareReport', 'myReports', 'noReports', 'startAnalysis',
      // FS3 会员守卫（R15-VA-N1 bonus_remaining 展示）与上传 phase 文案
      'quotaRemaining', 'bonusRemaining', 'confirming', 'creatingTask',
    ]
    const missing = expected.filter((k) => !(k in analysisZh))
    expect(missing).toEqual([])
  })

  it('analysis.step.* 覆盖流水线 10 步全部文案', () => {
    const stepZh = (zhCN.analysis as Record<string, any>).step
    const expected = [
      'videoUpload', 'transcode', 'ballDetect', 'speedEstimate', 'ballTrack',
      'actionRecognize', 'landingAnalyze', 'rallySplit', 'statistics', 'report',
    ]
    expect(Object.keys(stepZh)).toEqual(expect.arrayContaining(expected))
  })

  it('technique 域 7 个技术动作名齐备（跨模块复用）', () => {
    const techniqueZh = zhCN.technique as Record<string, string>
    const expected = [
      'forehand_drive', 'backhand_drive', 'forehand_loop',
      'backhand_loop', 'serve', 'push', 'block',
    ]
    const missing = expected.filter((k) => !(k in techniqueZh))
    expect(missing).toEqual([])
    const techniqueEn = enUS.technique as Record<string, string>
    expect(expected.filter((k) => !(k in techniqueEn))).toEqual([])
  })
})

describe('FS4 域 key 存在性（dashboard.* / progress.*）', () => {
  it('dashboard 域核心 key 齐备（概览/趋势/技术统计/热图/比赛记录）', () => {
    const dashboardZh = zhCN.dashboard as Record<string, any>
    const expected = [
      'title', 'winRate', 'wins', 'losses', 'analysisCount', 'trainingFreq',
      'timesPerWeek', 'streakDays', 'days', 'times',
      'winRateTrend', 'month', 'quarter', 'year',
      'techniqueStats', 'landingHeatmap', 'matchRecords', 'totalMatches',
      'allMatches', 'winsOnly', 'lossesOnly', 'win', 'lose', 'total',
      'totalRallies', 'sourceReports', 'forehand', 'backhand', 'middle',
      'hasIssues', 'noMatchData', 'noTechniqueData', 'noHeatmapData',
      'noMatchRecords', 'unknownOpponent', 'rating',
    ]
    const missing = expected.filter((k) => !(k in dashboardZh))
    expect(missing).toEqual([])
  })

  it('dashboard.cell.* 覆盖九宫格 9 个标签（GRID_CELL_LABELS 全量）', () => {
    const cellZh = (zhCN.dashboard as Record<string, any>).cell
    const expected = [
      'leftShort', 'midShort', 'rightShort',
      'leftMid', 'midMid', 'rightMid',
      'leftLong', 'midLong', 'rightLong',
    ]
    expect(Object.keys(cellZh)).toEqual(expect.arrayContaining(expected))
  })

  it('progress 域核心 key 齐备（摘要/对比/趋势详情）', () => {
    const progressZh = zhCN.progress as Record<string, any>
    const expected = [
      'summaryPeriod', 'totalAnalyses', 'overallProgress', 'metricTrends',
      'problemChanges', 'forecast', 'predictedWeeks', 'currentValue', 'target',
      'targetProgress', 'changeRate', 'persistenceCount', 'timeSeries', 'noData',
      'newProblems', 'resolvedProblems', 'persistentProblems', 'none',
      'reportA', 'reportB', 'selectReport', 'selectTwoReports', 'startComparison',
      'techniqueStats', 'landing', 'rally', 'ballSpeed', 'scoreAnalysis',
      'avgRallyLength', 'avgBallSpeed', 'winRate',
    ]
    const missing = expected.filter((k) => !(k in progressZh))
    expect(missing).toEqual([])
  })

  it('progress.period.* 覆盖后端 summary_period 全部取值（含 no_data/recent/last_3_months）', () => {
    const periodZh = (zhCN.progress as Record<string, any>).period
    const expected = ['month', 'quarter', 'year', 'all', 'recent', 'last_3_months', 'no_data']
    expect(Object.keys(periodZh)).toEqual(expect.arrayContaining(expected))
  })

  it('progress.trend.* 覆盖后端 trend 全部取值', () => {
    const trendZh = (zhCN.progress as Record<string, any>).trend
    const expected = ['improving', 'stagnant', 'declining', 'achieved', 'new', 'resolved']
    expect(Object.keys(trendZh)).toEqual(expect.arrayContaining(expected))
  })

  it('progress.metric.* 覆盖 comparison 渲染所需 6 个指标键（technique_stats 3 + landing 3）', () => {
    const metricZh = (zhCN.progress as Record<string, any>).metric
    const expected = [
      'forehand_ratio', 'backhand_ratio', 'serve_ratio',
      'landing_forehand_pct', 'landing_backhand_pct', 'landing_middle_pct',
    ]
    const missing = expected.filter((k) => !(k in metricZh))
    expect(missing).toEqual([])
  })

  it('common.back 存在（trend-detail 40415 错误分支返回按钮）', () => {
    expect((zhCN.common as Record<string, string>).back).toBeTruthy()
    expect((enUS.common as Record<string, string>).back).toBeTruthy()
  })
})

/** R2-P3-24（批次I）：批次E/F/G/H 新增键显式域断言。
 *  结构守卫（zh/en 集合相等 + 值非空）已能拦截单侧缺失，本组把「哪一批、
 *  哪个域」落成显式清单——回归失败时直接定位缺失键归属，不再依赖全量 diff 排查。
 *  zh/en 双侧同断（批次新键历史上有过单侧漏配先例，双断收紧）。 */
const resolve = (obj: Record<string, any>, path: string) =>
  path.split('.').reduce<any>((acc, seg) => acc?.[seg], obj)
const expectBatchKeys = (path: string, expected: string[]) => {
  const zhDom = resolve(zhCN, path) ?? {}
  const enDom = resolve(enUS, path) ?? {}
  // 失败时 diff 即缺失键清单（filter 产物），路径归属见用例名
  expect(expected.filter((k) => !(k in zhDom))).toEqual([])
  expect(expected.filter((k) => !(k in enDom))).toEqual([])
}

describe('R-FE-R2 批次E/F/G/H 新键域断言（回归定位提速）', () => {
  it('批次E home：周训练计数 + 打卡 CTA（FE-P3-20/21，批次H PointsCard 同页消费）', () => {
    expectBatchKeys('home', ['weeklyCount', 'viewPlan', 'checkinNow', 'todayCheckedIn'])
  })

  it('批次E scoring.setup：你的信息只读区（FE-P3-27，profile.kqs_rating 契约）', () => {
    expectBatchKeys('scoring', [
      'yourInfo', 'myPoints', 'opponentName', 'opponentNamePlaceholder',
      'opponentRating', 'opponentRatingPlaceholder',
    ])
  })

  it('批次E user：注销冷静期横幅键族（FE-P3-33 DeletionCoolingBanner 两页消费）', () => {
    expectBatchKeys('user', [
      'deletionCoolingTitle', 'deletionCoolingDesc', 'deletionCountdown',
      'deletionExecuted', 'cancelDeletion', 'deletionCancelled', 'deletionCancelFailed',
    ])
  })

  it('批次E training：plans/detail 调整历史（FE-P3-32，ADJUSTMENT_ACTION_MAP 消费面）', () => {
    expectBatchKeys('training', ['adjustmentHistory', 'reEvaluate', 'reEvaluateFailed'])
  })

  it('批次E membership：tiers 失败/空态引导（FE-P3-34）', () => {
    expectBatchKeys('membership', ['tiersEmpty', 'benefit', 'subscribe'])
  })

  it('批次G scoring：对手打法四选项（FE-P2-14 OPPONENT_STYLE_OPTIONS labelKey 全集）', () => {
    expectBatchKeys('scoring', [
      'opponentPlayingStyle', 'playStyle_unselected', 'playStyle_fast_attack',
      'playStyle_loop_drive', 'playStyle_chop', 'playStyle_all_round',
    ])
  })

  it('批次G analysis：热图双源 / 节奏曲线 / 关键分标记（FE-P1-3/P2-5/P2-6）', () => {
    expectBatchKeys('analysis', [
      'myLanding', 'opponentLanding', 'tempoCurve', 'tempoHint', 'keyPoints', 'keyPointSeek',
    ])
  })

  it('批次H gamification：积分流水最近动态 + 徽章分类 chip（R2-P2-1/2）', () => {
    expectBatchKeys('gamification', [
      'sourceOther', 'recentActivity',
      'categoryAnalysis', 'categoryMatch', 'categoryStreak', 'categoryGeneral',
    ])
  })

  it('批次E/H progress.metric：METRIC_DEFINITIONS 18 键全集（R2-P2-3，progress_service.py:29-46）', () => {
    expectBatchKeys('progress.metric', [
      'forehand_ratio', 'backhand_ratio', 'serve_ratio',
      'landing_forehand_pct', 'landing_backhand_pct', 'landing_middle_pct', 'landing_dispersion',
      'avg_rally_length', 'max_rally_length', 'rally_frequency',
      'avg_ball_speed', 'max_ball_speed',
      'score_win_rate', 'key_point_win_rate',
      'serve_point_win_rate', 'receive_point_win_rate', 'attack_transition_rate', 'error_rate',
    ])
  })
})
