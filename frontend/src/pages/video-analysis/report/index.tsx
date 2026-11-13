/**
 * 分析报告详情页（03-video_analysis/frontend.md §4.3）
 * 指标卡 + 落点九宫格热图 + 技术动作环形图（CSS conic-gradient 实现）+ 球速 +
 * 分析结论 + 视频回放 + is_correct 反馈（数据飞轮）+ 分享
 *
 * FS3-P3 契约修正：
 * - 技术环形图以 conic-gradient 实现（设计样例 clipPath polygon 为同弧度模板，
 *   多分段数学不正确）；中心挖洞用内层圆形 View
 * - NutUI 2.7.14 文本域组件为 TextArea（设计样例 Textarea 为 1.x 命名）
 * - is_readonly（会员到期降级，R15）展示分支归 FS6 会员 Sprint 消费
 */
import { useEffect, useRef, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView, Video } from '@tarojs/components'
import { Button, Toast, Popup, Skeleton, TextArea } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import BadgeUnlockPopup from '@/components/BadgeUnlockPopup'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function ReportPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const reportId = parseInt((router.params.report_id || '0') as string, 10)
  const reportDetail = useVideoAnalysisStore((s) => s.reportDetail)
  const feedbackSubmitted = useVideoAnalysisStore((s) => s.feedbackSubmitted)
  const fetchReportDetail = useVideoAnalysisStore((s) => s.fetchReportDetail)
  const submitFeedback = useVideoAnalysisStore((s) => s.submitFeedback)
  const createShare = useVideoAnalysisStore((s) => s.createShare)

  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  const [feedbackPopupVisible, setFeedbackPopupVisible] = useState(false)
  const [feedbackComment, setFeedbackComment] = useState('')
  // R-FE-R2 批次G（FE-P1-3）：落点热图双源切换（03 frontend.md §4.3 L873-886）
  const [landingView, setLandingView] = useState<'mine' | 'opponent'>('mine')
  // R-FE-R2 批次G（FE-P2-6）：视频上下文懒建（marker 点击 seek 消费）
  const videoCtxRef = useRef<ReturnType<typeof Taro.createVideoContext> | null>(null)

  useEffect(() => {
    if (reportId) fetchReportDetail(reportId)
  }, [reportId, fetchReportDetail])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 提交反馈 */
  const handleFeedback = async (isCorrect: boolean) => {
    try {
      await submitFeedback(reportId, isCorrect, feedbackComment || undefined)
      setFeedbackPopupVisible(false)
      showToast(isCorrect ? t('analysis.feedbackCorrect') : t('analysis.feedbackIncorrect'))
    } catch (err: any) {
      showToast(err?.message || t('common.operationFailed'))
    }
  }

  /** 分享报告（share_url 复制到剪贴板） */
  const handleShare = async () => {
    try {
      const { share_url } = await createShare(reportId)
      Taro.setClipboardData({ data: share_url })
      showToast(t('analysis.shareLinkCopied'))
    } catch (err: any) {
      showToast(err?.message || t('common.operationFailed'))
    }
  }

  if (!reportDetail || reportDetail.id !== reportId) {
    return (
      <View className="report-loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const result = reportDetail.result_data
  const reportText = reportDetail.report_text
  const landing = result?.landing_points
  const techniques = result?.technique_stats
  const ballSpeed = result?.ball_speed
  const rally = result?.rally_analysis

  // R-FE-R2 批次G（FE-P1-3）：热图双源——优先 landing_heatmap（含对手侧），
  // 旧报告回落 landing_points.nine_grid；对手侧缺省不渲染 toggle（向后兼容）
  const heatmap = result?.landing_heatmap
  const myGrid = heatmap?.nine_grid?.length ? heatmap.nine_grid : landing?.nine_grid
  const oppGrid = heatmap?.opponent_nine_grid?.length ? heatmap.opponent_nine_grid : null
  const activeGrid = landingView === 'opponent' ? oppGrid : myGrid

  // 九宫格热图颜色深浅（主色 #E63946 RGB，JS 无法读 CSS 变量）
  const PRIMARY_RGB = '230, 57, 70'
  const maxLanding = activeGrid ? Math.max(...activeGrid.flat()) : 1
  const getHeatColor = (val: number) => {
    const ratio = maxLanding > 0 ? val / maxLanding : 0
    const alpha = 0.2 + ratio * 0.8
    return `rgba(${PRIMARY_RGB}, ${alpha})`
  }

  // R-FE-R2 批次G（FE-P2-5）：节奏曲线几何——weapp 不支持 <svg>，按 conic 先例
  // 用绝对定位 View 旋转线段绘折线（300×120 画布居中，段端点按数据归一化计算）
  const tempo = rally?.rally_tempo ?? []
  const TEMPO_W = 300
  const TEMPO_H = 120
  const TEMPO_PAD = 14
  const tempoPts = tempo.length > 1
    ? tempo.map((v, i) => {
        const minV = Math.min(...tempo)
        const maxV = Math.max(...tempo)
        const span = maxV - minV || 1
        return {
          x: TEMPO_PAD + (i * (TEMPO_W - 2 * TEMPO_PAD)) / (tempo.length - 1),
          y: TEMPO_H - TEMPO_PAD - ((v - minV) / span) * (TEMPO_H - 2 * TEMPO_PAD),
        }
      })
    : []
  const tempoSegments = tempoPts.slice(0, -1).map((p, i) => {
    const q = tempoPts[i + 1]
    const dx = q.x - p.x
    const dy = q.y - p.y
    return {
      key: `seg-${i}`,
      left: p.x,
      top: p.y,
      width: Math.sqrt(dx * dx + dy * dy),
      angle: (Math.atan2(dy, dx) * 180) / Math.PI,
    }
  })

  // R-FE-R2 批次G（FE-P2-6）：关键分 marker（timestamp 为视频相对秒，
  // 旧报告无时间戳的条目不渲染——marker 语义即点击回放）
  const keyPoints =
    result?.score_analysis?.key_points?.filter(
      (kp): kp is typeof kp & { timestamp: number } => kp.timestamp != null
    ) ?? []

  /** marker 点击 → 视频跳转到关键分时刻 */
  const seekTo = (sec: number) => {
    if (!videoCtxRef.current) {
      videoCtxRef.current = Taro.createVideoContext('annotated-video')
    }
    videoCtxRef.current?.seek(sec)
    videoCtxRef.current?.play()
  }

  /** 关键分时刻格式化（m:ss） */
  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}:${String(s).padStart(2, '0')}`
  }

  // 技术统计环形图（conic-gradient 分段 + 内圆挖洞）
  const techniqueTotal = techniques
    ? Object.values(techniques).reduce((a, b) => a + b, 0)
    : 1
  const SEGMENT_COLORS = [
    'var(--color-primary)',
    'var(--color-secondary)',
    'var(--color-accent)',
    'var(--color-success)',
  ]
  const buildDonutGradient = (stats: Record<string, number>): string => {
    let acc = 0
    const stops: string[] = []
    Object.values(stats).forEach((val, idx) => {
      const pct = (val / techniqueTotal) * 100
      // 显式色值百分比插值（conic-gradient 变量在 weapp WebView 支持不稳，改用固定色板）
      const colorHex = ['#E63946', '#2A9D8F', '#F4A261', '#457B9D'][idx % 4]
      stops.push(`${colorHex} ${acc}%, ${colorHex} ${acc + pct}%`)
      acc += pct
    })
    return `conic-gradient(${stops.join(', ')})`
  }

  return (
    <ScrollView scrollY className="report-page">
      {/* 报告头部 */}
      <View className="report-header">
        <Text className="report-date">
          {reportDetail.created_at ? new Date(reportDetail.created_at).toLocaleDateString() : ''}
          {reportDetail.is_llm_generated && <Text className="llm-tag">{t('analysis.aiGenerated')}</Text>}
        </Text>
        {result?.video_info && (
          <Text className="video-info">
            {t('analysis.duration')}: {`${Math.floor(result.video_info.duration_sec / 60)}'${result.video_info.duration_sec % 60}"`}
          </Text>
        )}
      </View>

      {/* 核心数据卡片 */}
      <View className="core-data-section">
        <View className="data-card">
          <Text className="data-value">{rally?.total_rallies || 0}</Text>
          <Text className="data-label">{t('analysis.totalRallies')}</Text>
        </View>
        <View className="data-card">
          <Text className="data-value">{rally?.avg_rally_length?.toFixed(1) || '0'}</Text>
          <Text className="data-label">{t('analysis.avgRallyLength')}</Text>
        </View>
        <View className="data-card">
          <Text className="data-value">{rally?.max_rally_length || 0}</Text>
          <Text className="data-label">{t('analysis.maxRallyLength')}</Text>
        </View>
      </View>

      {/* 落点九宫格热图（R-FE-R2 批次G FE-P1-3：mine/opponent 双源切换，§4.3 L873-886） */}
      {activeGrid && (
        <View className="heatmap-section">
          <View className="section-title">{t('analysis.landingDistribution')}</View>
          {oppGrid && (
            <View className="heatmap-toggle">
              <View
                className={`toggle-btn ${landingView === 'mine' ? 'active' : ''}`}
                onClick={() => setLandingView('mine')}
              >
                <Text>{t('analysis.myLanding')}</Text>
              </View>
              <View
                className={`toggle-btn ${landingView === 'opponent' ? 'active' : ''}`}
                onClick={() => setLandingView('opponent')}
              >
                <Text>{t('analysis.opponentLanding')}</Text>
              </View>
            </View>
          )}
          <View className="heatmap-grid" role="img" aria-label={t('analysis.landingDistribution')}>
            {activeGrid.map((row, ri) =>
              row.map((val, ci) => (
                <View
                  key={`${ri}-${ci}`}
                  className="heatmap-cell"
                  style={{ background: getHeatColor(val) }}
                >
                  <Text className="cell-value">{val}</Text>
                </View>
              ))
            )}
          </View>
          {/* R23-P2-1：仅传入 forehand 参数（资源文件无 {{side}} 占位符）；
              distribution 属我的落点语境，对手视图不渲染 */}
          {landingView === 'mine' && landing && (
            <Text className="heatmap-hint">
              {t('analysis.landingHint', {
                forehand: ((landing.distribution.forehand || 0) * 100).toFixed(0),
              })}
            </Text>
          )}
        </View>
      )}

      {/* 技术动作环形图 */}
      {techniques && (
        <View className="technique-section">
          <View className="section-title">{t('analysis.techniqueDistribution')}</View>
          <View className="technique-chart">
            <View
              className="donut-chart"
              style={{ background: buildDonutGradient(techniques) }}
              role="img"
              aria-label={t('analysis.techniqueDistribution')}
            >
              <View className="donut-hole" />
            </View>
            <View className="technique-legend">
              {Object.entries(techniques).map(([key, val], idx) => {
                const pct = ((val / techniqueTotal) * 100).toFixed(0)
                return (
                  <View key={key} className="legend-item">
                    <View
                      className="legend-dot"
                      style={{ background: SEGMENT_COLORS[idx % SEGMENT_COLORS.length] }}
                    />
                    <Text className="legend-label">{t(`technique.${key}`)}</Text>
                    <Text className="legend-value">{pct}%</Text>
                  </View>
                )
              })}
            </View>
          </View>
          {reportText && reportText.issues.length > 0 && (
            <Text className="technique-hint">{reportText.issues[0]}</Text>
          )}
        </View>
      )}

      {/* 球速数据（范围值） */}
      {ballSpeed && (
        <View className="ball-speed-section">
          <View className="section-title">{t('analysis.ballSpeed')}</View>
          <View className="speed-display">
            <Text className="speed-range">
              {ballSpeed.speed_range[0].toFixed(1)} - {ballSpeed.speed_range[1].toFixed(1)}
            </Text>
            <Text className="speed-unit">m/s</Text>
          </View>
          <Text className="speed-hint">{t('analysis.speedHint')}</Text>
        </View>
      )}

      {/* 回合节奏曲线（R-FE-R2 批次G FE-P2-5：v2.0 T2.3；rally_tempo 序列，
          weapp 无 svg 支持按 conic 先例用 View 旋转线段绘折线） */}
      {tempoSegments.length > 0 && (
        <View className="tempo-section">
          <View className="section-title">{t('analysis.tempoCurve')}</View>
          <View className="tempo-chart">
            {tempoSegments.map((seg) => (
              <View
                key={seg.key}
                className="tempo-segment"
                style={{
                  left: `${seg.left}px`,
                  top: `${seg.top}px`,
                  width: `${seg.width}px`,
                  transform: `rotate(${seg.angle}deg)`,
                }}
              />
            ))}
            {tempoPts.map((p, i) => (
              <View key={`dot-${i}`} className="tempo-dot" style={{ left: `${p.x}px`, top: `${p.y}px` }} />
            ))}
          </View>
          <Text className="tempo-hint">{t('analysis.tempoHint')}</Text>
        </View>
      )}

      {/* 分析结论 */}
      {reportText && (
        <View className="conclusion-section">
          <View className="section-title">{t('analysis.conclusion')}</View>
          <View className="conclusion-content">
            <Text className="conclusion-summary">{reportText.summary}</Text>
            {reportText.issues.length > 0 && (
              <View className="issues-list">
                <Text className="issues-title">{t('analysis.issues')}</Text>
                {reportText.issues.map((issue, idx) => (
                  <Text key={idx} className="issue-item">• {issue}</Text>
                ))}
              </View>
            )}
          </View>
          {reportText.suggestions.length > 0 && (
            <View className="suggestions-list">
              <Text className="suggestions-title">{t('analysis.suggestions')}</Text>
              {reportText.suggestions.map((suggestion, idx) => (
                <Text key={idx} className="suggestion-item">• {suggestion}</Text>
              ))}
            </View>
          )}
        </View>
      )}

      {/* 视频回放（R-FE-R2 批次G FE-P2-6：关键分 marker 点击 seek 回放） */}
      {reportDetail.annotated_video_url && (
        <View className="video-section">
          <View className="section-title">{t('analysis.videoPlayback')}</View>
          <Video
            id="annotated-video"
            src={reportDetail.annotated_video_url}
            controls
            autoplay={false}
            className="annotated-video"
          />
          {keyPoints.length > 0 && (
            <View className="keypoint-list">
              <Text className="keypoint-title">
                {t('analysis.keyPoints')} · {t('analysis.keyPointSeek')}
              </Text>
              <ScrollView scrollX enhanced showScrollbar={false} className="keypoint-scroll">
                {keyPoints.map((kp) => (
                  <View
                    key={`kp-${kp.seq}`}
                    className="keypoint-chip"
                    onClick={() => seekTo(kp.timestamp)}
                  >
                    <Text className="chip-score">{kp.score}</Text>
                    <Text className="chip-meta">#{kp.seq} · {formatTime(kp.timestamp)}</Text>
                  </View>
                ))}
              </ScrollView>
            </View>
          )}
        </View>
      )}

      {/* 反馈区域（is_correct 数据飞轮；is_readonly 展示分支归 FS6 会员 Sprint） */}
      <View className="feedback-section">
        {feedbackSubmitted ? (
          <Text className="feedback-done">{t('analysis.feedbackSubmitted')}</Text>
        ) : (
          <>
            <Text className="feedback-title">{t('analysis.feedbackPrompt')}</Text>
            <View className="feedback-buttons">
              <Button type="success" onClick={() => handleFeedback(true)}>
                👍 {t('analysis.accurate')}
              </Button>
              <Button type="danger" onClick={() => setFeedbackPopupVisible(true)}>
                👎 {t('analysis.inaccurate')}
              </Button>
            </View>
          </>
        )}
      </View>

      {/* 底部操作 */}
      <View className="bottom-actions">
        {/* R-FE-R1 批次A（FE-P1-7）：报告 → 训练建议闭环（07-training §6.5 报告 →
            查看训练建议 → advice?report_id=，fetchAdviceByReport 现成能力） */}
        <Button
          type="default"
          block
          className="advice-btn"
          onClick={() =>
            Taro.navigateTo({ url: `/pages/training/advice/index?report_id=${reportId}` })
          }
        >
          {t('analysis.viewAdvice')}
        </Button>
        <Button type="primary" block onClick={handleShare}>
          {t('analysis.shareReport')}
        </Button>
      </View>

      {/* 反馈弹窗（部分不准 → 补充说明） */}
      <Popup
        visible={feedbackPopupVisible}
        position="bottom"
        onClose={() => setFeedbackPopupVisible(false)}
      >
        <View className="feedback-popup">
          <Text className="popup-title">{t('analysis.feedbackDetail')}</Text>
          <TextArea
            placeholder={t('analysis.feedbackPlaceholder')}
            value={feedbackComment}
            onChange={(val: string) => setFeedbackComment(val)}
            maxLength={500}
            className="feedback-textarea"
          />
          <Button type="primary" block onClick={() => handleFeedback(false)}>
            {t('common.submit')}
          </Button>
        </View>
      </Popup>

      {/* R-FE-R1 批次B（FE-P1-8）：徽章弹层补挂（analysis N 次类徽章触发时
          用户常位于报告页；useBadgeUnlock 共享单例监听无重复连接风险） */}
      <BadgeUnlockPopup />

      <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
    </ScrollView>
  )
}
