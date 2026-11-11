/**
 * 报告对比页（08-progress_analysis/frontend.md §4.2）
 * 快照 Picker 双选 + 6 维度对比（技术/落点/回合/球速/得分/问题变化）
 *
 * FS4-P3 契约修正（以后端为准）：
 * - comparisons.landing 键名为 forehand_pct/backhand_pct/middle_pct（R4-Progress-8），
 *   i18n 映射到 progress.metric.landing_* 键
 * - rally 含 max_length_a/b、ball_speed 含 max_a/b（设计样例仅展示 avg，此处一并展示）
 * - 相同报告 422/42201、报告不存在 404/40412 由 request 层抛错（message 透出）
 *
 * R-FE-R1 批次B（FE-P1-10② + FE-P2-25）：progress_analysis 会员门控（同 summary 页）。
 */
import { useEffect, useState } from 'react'
import { useRouter } from '@tarojs/taro'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Tag, Empty } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { useMembershipGate } from '@/hooks/useMembershipGate'
import { listSnapshots } from '@/services/progress'
import { useTranslation } from 'react-i18next'
import { formatPercent, formatChange } from '@/utils/chart'
import './index.scss'

/** comparison.landing 键名 → i18n metric 键映射（R4-Progress-8） */
const LANDING_LABEL_KEYS: Record<string, string> = {
  forehand_pct: 'progress.metric.landing_forehand_pct',
  backhand_pct: 'progress.metric.landing_backhand_pct',
  middle_pct: 'progress.metric.landing_middle_pct',
}

export default function ComparisonPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const comparison = useProgressStore((s) => s.comparison)
  const loading = useProgressStore((s) => s.loading)
  const fetchComparison = useProgressStore((s) => s.fetchComparison)
  // R-FE-R1 批次B（FE-P1-10②）：progress_analysis 会员门控
  const { canAccess } = useMembershipGate('progress_analysis')

  const [snapshots, setSnapshots] = useState<Array<{ id: number; report_id: number; created_at: string }>>([])
  const [reportA, setReportA] = useState<number | undefined>(
    router.params.report_a ? Number(router.params.report_a) : undefined
  )
  const [reportB, setReportB] = useState<number | undefined>(
    router.params.report_b ? Number(router.params.report_b) : undefined
  )

  useEffect(() => {
    listSnapshots({ page: 1, page_size: 50 }).then((res) => {
      setSnapshots(res.data.data.items)
    })
  }, [])

  useEffect(() => {
    if (reportA && reportB && reportA !== reportB) {
      fetchComparison(reportA, reportB)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportA, reportB])

  /** 变化值颜色（正值绿/负值红） */
  const changeColor = (change: number | null | undefined): string => {
    if (change == null) return 'var(--color-text-secondary)'
    if (change === 0) return 'var(--color-text-secondary)'
    return change > 0 ? 'var(--color-success)' : 'var(--color-primary)'
  }

  const snapshotLabels = snapshots.map((s) => `#${s.report_id} (${(s.created_at || '').slice(0, 10)})`)

  // 会员门控：免费/到期/闭户 → 升级引导（R-FE-R1 批次B，同 summary 页先例）
  if (!canAccess) {
    return (
      <View className="comparison-page">
        <View className="membership-guard">
          <Empty
            title={t('progress.membershipRequired')}
            actions={[
              {
                text: t('progress.upgradeMembership'),
                type: 'primary',
                size: 'small',
                onClick: () => Taro.navigateTo({ url: '/pages/membership/index' }),
              },
            ]}
          />
        </View>
      </View>
    )
  }

  return (
    <View className="comparison-page">
      {/* 报告选择区 */}
      <View className="report-selector">
        <Picker
          mode="selector"
          range={snapshotLabels}
          onChange={(e) => setReportA(snapshots[Number(e.detail.value)]?.report_id)}
        >
          <Cell
            title={t('progress.reportA')}
            clickable
            extra={<Text className="picker-value">{reportA ? `#${reportA}` : t('progress.selectReport')}</Text>}
          />
        </Picker>
        <Picker
          mode="selector"
          range={snapshotLabels}
          onChange={(e) => setReportB(snapshots[Number(e.detail.value)]?.report_id)}
        >
          <Cell
            title={t('progress.reportB')}
            clickable
            extra={<Text className="picker-value">{reportB ? `#${reportB}` : t('progress.selectReport')}</Text>}
          />
        </Picker>
        <Button
          type="primary"
          block
          disabled={!reportA || !reportB || reportA === reportB}
          loading={loading}
          onClick={() => reportA && reportB && fetchComparison(reportA, reportB)}
        >
          {t('progress.startComparison')}
        </Button>
      </View>

      {/* 对比结果区 */}
      {comparison ? (
        <View className="comparison-result">
          {/* 维度 1：技术统计对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.techniqueStats')}</Text>
            {Object.entries(comparison.comparisons.technique_stats).map(([key, val]) => (
              <View key={key} className="comparison-row">
                <Text className="row-label">{t(`progress.metric.${key}`)}</Text>
                <View className="row-values">
                  <Text className="value-a">{formatPercent(val.a, 1)}</Text>
                  <Text className="value-arrow">→</Text>
                  <Text className="value-b">{formatPercent(val.b, 1)}</Text>
                  <Text style={{ color: changeColor(val.change) }}>{formatChange(val.change)}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* 维度 2：落点对比（键名 forehand_pct 等，R4-Progress-8） */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.landing')}</Text>
            {Object.entries(comparison.comparisons.landing).map(([key, val]) => (
              <View key={key} className="comparison-row">
                <Text className="row-label">{t(LANDING_LABEL_KEYS[key] || `progress.metric.${key}`)}</Text>
                <View className="row-values">
                  <Text className="value-a">{formatPercent(val.a, 1)}</Text>
                  <Text className="value-arrow">→</Text>
                  <Text className="value-b">{formatPercent(val.b, 1)}</Text>
                  <Text style={{ color: changeColor(val.change) }}>{formatChange(val.change)}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* 维度 3：回合对比（含 max，FS4-P3） */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.rally')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.avgRallyLength')}</Text>
              <View className="row-values">
                <Text className="value-a">{comparison.comparisons.rally.avg_length_a ?? '-'}</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{comparison.comparisons.rally.avg_length_b ?? '-'}</Text>
                <Text style={{ color: changeColor(comparison.comparisons.rally.change) }}>
                  {comparison.comparisons.rally.change != null
                    ? `${comparison.comparisons.rally.change > 0 ? '+' : ''}${comparison.comparisons.rally.change}`
                    : '-'}
                </Text>
              </View>
            </View>
          </View>

          {/* 维度 4：球速对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.ballSpeed')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.avgBallSpeed')}</Text>
              <View className="row-values">
                <Text className="value-a">{comparison.comparisons.ball_speed.avg_a ?? '-'} m/s</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{comparison.comparisons.ball_speed.avg_b ?? '-'} m/s</Text>
                <Text style={{ color: changeColor(comparison.comparisons.ball_speed.change) }}>
                  {comparison.comparisons.ball_speed.change != null
                    ? `${comparison.comparisons.ball_speed.change > 0 ? '+' : ''}${comparison.comparisons.ball_speed.change}`
                    : '-'}
                </Text>
              </View>
            </View>
          </View>

          {/* 维度 5：得分对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.scoreAnalysis')}</Text>
            <View className="comparison-row">
              <Text className="row-label">{t('progress.winRate')}</Text>
              <View className="row-values">
                <Text className="value-a">{formatPercent(comparison.comparisons.score_analysis.win_rate_a)}</Text>
                <Text className="value-arrow">→</Text>
                <Text className="value-b">{formatPercent(comparison.comparisons.score_analysis.win_rate_b)}</Text>
                <Text style={{ color: changeColor(comparison.comparisons.score_analysis.change) }}>
                  {formatChange(comparison.comparisons.score_analysis.change)}
                </Text>
              </View>
            </View>
          </View>

          {/* 维度 6：问题变化对比 */}
          <View className="comparison-section">
            <Text className="section-title">{t('progress.problemChanges')}</Text>
            <View className="problem-changes">
              <View className="problem-group">
                <Tag background="var(--color-primary)" color="var(--color-text-inverse)">
                  {t('progress.newProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.new.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.new.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
              <View className="problem-group">
                <Tag background="var(--color-success)" color="var(--color-text-inverse)">
                  {t('progress.resolvedProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.resolved.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.resolved.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
              <View className="problem-group">
                <Tag background="var(--color-warning)" color="var(--color-text-inverse)">
                  {t('progress.persistentProblems')}
                </Tag>
                {comparison.comparisons.problem_changes.persistent.map((p, i) => (
                  <Text key={i} className="problem-item">• {p}</Text>
                ))}
                {comparison.comparisons.problem_changes.persistent.length === 0 && (
                  <Text className="empty-item">{t('progress.none')}</Text>
                )}
              </View>
            </View>
          </View>
        </View>
      ) : !loading ? (
        <Empty description={t('progress.selectTwoReports')} />
      ) : null}
    </View>
  )
}
