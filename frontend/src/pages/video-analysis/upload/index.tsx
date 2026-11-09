/**
 * 视频上传页（03-video_analysis/frontend.md §4.1）
 * 拍摄引导 → chooseVideo 校验 → STS 直传 OSS → upload-complete 确认 → 创建任务
 *
 * FS3-P3 契约修正：
 * - OSS 直传地址为后端签发的 upload_url（Mock 环境指向 localhost:3000/mock-oss/{oss_key}，
 *   真实 OSS S6+ 接入），formData 按设计样例 STS PostObject 字段组装
 * - 文件大小校验双侧兜底：前端 500MB 上限 + 后端 400/422 错误分支
 * - 会员守卫：展示免费额度 remaining + 付费包 bonus_remaining（R15-VA-N1），耗尽引导购买
 */
import { useState, useCallback, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Toast, Progress } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { getQuota } from '@/services/user'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function UploadPage() {
  const { t } = useTranslation()
  const {
    uploadPhase,
    uploadProgress,
    getUploadToken,
    setUploadProgress,
    confirmUpload,
    createTask,
    resetUpload,
  } = useVideoAnalysisStore()

  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  // 会员守卫：免费日额度 + 付费包余额（R15-VA-N1）
  const [quotaRemaining, setQuotaRemaining] = useState<number | null>(null)
  const [bonusRemaining, setBonusRemaining] = useState<number | null>(null)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  // 进入页面拉取额度状态（会员守卫展示层）
  useEffect(() => {
    getQuota()
      .then((res) => {
        setQuotaRemaining(res.data.data.remaining)
        setBonusRemaining(res.data.data.bonus_remaining)
      })
      .catch(() => {
        // 额度展示失败不阻塞上传入口（创建任务时后端仍会校验额度）
      })
  }, [])

  /** OSS 直传 + 确认 + 创建任务 */
  const startUpload = useCallback(
    async (filePath: string, fileSize: number, filename: string) => {
      try {
        // 1. 获取上传凭证（后端签发 file_id + oss_key + STS + upload_url）
        const { file_id, oss_key, sts_credentials, upload_url } = await getUploadToken(
          filename,
          fileSize
        )

        // 2. 直传 OSS（PostObject 表单；Mock 环境为本地 mock-oss）
        const uploadTask = Taro.uploadFile({
          url: upload_url,
          filePath,
          name: 'file',
          formData: {
            key: oss_key,
            OSSAccessKeyId: sts_credentials.access_key_id,
            policy: '',
            Signature: sts_credentials.access_key_secret,
            'x-oss-security-token': sts_credentials.security_token,
          },
          success: () => {
            // 3. 确认上传（后端 HEAD Object 校验）→ 创建任务
            confirmAndCreateTask(file_id, oss_key)
          },
          fail: () => {
            showToast(t('analysis.uploadFailed'))
            resetUpload()
          },
        })

        // 上传进度（百分比 0-100）
        uploadTask.progress((res) => {
          setUploadProgress(res.progress)
        })
      } catch (err: any) {
        showToast(err?.message || t('analysis.uploadFailed'))
        resetUpload()
      }
    },
    [getUploadToken, setUploadProgress, confirmUpload, createTask, resetUpload, t]
  )

  /** 确认上传 + 创建任务 → 跳进度页 */
  const confirmAndCreateTask = useCallback(
    async (fileId: number, ossKey: string) => {
      try {
        await confirmUpload(fileId)
        const result = await createTask(fileId, ossKey)
        showToast(t('analysis.taskCreated'))
        // 跳转到进度页（task_id 为 int）
        setTimeout(() => {
          Taro.redirectTo({ url: `/pages/video-analysis/processing/index?task_id=${result.task_id}` })
        }, 1500)
      } catch (err: any) {
        showToast(err?.message || t('analysis.taskCreateFailed'))
        resetUpload()
      }
    },
    [confirmUpload, createTask, resetUpload, t]
  )

  /** 选择/拍摄视频（类型/大小/时长校验） */
  const handleChooseVideo = useCallback(() => {
    Taro.chooseVideo({
      sourceType: ['album', 'camera'],
      maxDuration: 300, // 5 分钟（chooseVideo 秒级上限）
      camera: 'back',
      success: (res) => {
        // FS8-P0 修复：Taro H5 chooseVideo 的 tempFilePath 为 createObjectURL 的 blob URL
        // （无扩展名，res 无 name 字段），扩展名校验在 H5 恒失败导致上传入口不可用——
        // H5 端跳过扩展名校验（后端 upload-token/oss 422 校验兜底），filename 用固定参考名。
        // （weapp 端 tempFilePath 带真实扩展名，保留原校验逻辑）
        if (process.env.TARO_ENV !== 'h5') {
          // 校验文件类型（Mock/真实 OSS 均仅收 mp4/mov）
          if (!res.tempFilePath.toLowerCase().match(/\.(mp4|mov)$/)) {
            showToast(t('analysis.invalidFormat'))
            return
          }
        }
        // 校验文件大小（≤500MB；后端另有 <1MB 422 校验）
        if (res.size > 500 * 1024 * 1024) {
          showToast(t('analysis.fileTooLarge'))
          return
        }
        // weapp：Taro.chooseVideo 返回无 name 字段（weapp 类型契约），从临时路径提取文件名
        // h5：blob URL 无文件名语义，用固定参考名（oss_key 由后端生成，filename 仅参考）
        const filename =
          process.env.TARO_ENV === 'h5'
            ? 'video.mp4'
            : res.tempFilePath.split('/').pop() || 'video.mp4'
        startUpload(res.tempFilePath, res.size, filename)
      },
      fail: (err) => {
        if (err.errMsg !== 'chooseVideo:fail cancel') {
          showToast(t('analysis.chooseFailed'))
        }
      },
    })
  }, [startUpload, t])

  // 拍摄引导界面
  if (uploadPhase === 'idle') {
    return (
      <View className="upload-page">
        {/* 拍摄引导 */}
        <View className="guide-section">
          <Text className="guide-title">{t('analysis.shootingGuide')}</Text>
          <View className="guide-cards">
            <View className="guide-card">
              <Text className="guide-icon">📐</Text>
              <Text className="guide-text">{t('analysis.angleGuide')}</Text>
              <Text className="guide-detail">{t('analysis.angleDetail')}</Text>
            </View>
            <View className="guide-card">
              <Text className="guide-icon">📏</Text>
              <Text className="guide-text">{t('analysis.distanceGuide')}</Text>
              <Text className="guide-detail">{t('analysis.distanceDetail')}</Text>
            </View>
            <View className="guide-card">
              <Text className="guide-icon">💡</Text>
              <Text className="guide-text">{t('analysis.lightingGuide')}</Text>
              <Text className="guide-detail">{t('analysis.lightingDetail')}</Text>
            </View>
          </View>
        </View>

        {/* 注意事项 */}
        <View className="notice-section">
          <Text className="notice-title">{t('analysis.notice')}</Text>
          <View className="notice-list">
            <Text className="notice-item">• {t('analysis.noticeFormat')}</Text>
            <Text className="notice-item">• {t('analysis.noticeSize')}</Text>
            <Text className="notice-item">• {t('analysis.noticeDuration')}</Text>
          </View>
        </View>

        {/* 额度状态（会员守卫：免费日额度 + 付费包余额，R15-VA-N1） */}
        <View className="quota-section">
          <Text className="quota-text">{t('analysis.freeQuotaHint')}</Text>
          {quotaRemaining !== null && (
            <Text className="quota-remaining">
              {t('analysis.quotaRemaining', { count: quotaRemaining })}
            </Text>
          )}
          {bonusRemaining !== null && bonusRemaining > 0 && (
            <Text className="quota-bonus">{t('analysis.bonusRemaining', { count: bonusRemaining })}</Text>
          )}
        </View>

        <Button type="primary" block className="upload-btn" onClick={handleChooseVideo}>
          {t('analysis.chooseVideo')}
        </Button>

        <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
      </View>
    )
  }

  // 上传中界面（uploading / confirming / creating_task）
  if (uploadPhase === 'uploading' || uploadPhase === 'confirming' || uploadPhase === 'creating_task') {
    const phaseText =
      uploadPhase === 'uploading'
        ? t('analysis.uploading')
        : uploadPhase === 'confirming'
          ? t('analysis.confirming')
          : t('analysis.creatingTask')
    return (
      <View className="uploading-page">
        <View className="uploading-content">
          <Text className="uploading-icon">📹</Text>
          <Text className="uploading-text">{phaseText}</Text>
          <Progress
            percent={uploadProgress}
            color="var(--color-primary)"
            strokeWidth="8px"
            aria-label={t('analysis.uploading')}
          />
        </View>
      </View>
    )
  }

  return null
}
