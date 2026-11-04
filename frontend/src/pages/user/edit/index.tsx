/**
 * 档案编辑页（02-user/frontend.md §4.2）
 * 打法 / 自评水平 / 装备配置编辑
 */
import { useState, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Button, Toast, Input } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

const PLAYING_STYLES = [
  { value: 'loop', labelKey: 'user.style_loop' },
  { value: 'quick_attack', labelKey: 'user.style_quick_attack' },
  { value: 'chop', labelKey: 'user.style_chop' },
  { value: 'allround', labelKey: 'user.style_allround' },
]

const SELF_LEVELS = [
  { value: 'beginner', labelKey: 'user.level_beginner' },
  { value: 'intermediate', labelKey: 'user.level_intermediate' },
  { value: 'advanced', labelKey: 'user.level_advanced' },
]

// P1-FE3 i18n：常量层无法使用 useTranslation hook，使用 labelKey 替代 label，
// 组件渲染时通过 t(item.labelKey) 获取本地化文本

export default function ProfileEditPage() {
  const { t } = useTranslation()
  const { profile, updateProfile, fetchProfile } = useUserStore()
  const [playingStyle, setPlayingStyle] = useState('')
  const [selfLevel, setSelfLevel] = useState('')
  const [bladeBrand, setBladeBrand] = useState('')
  const [bladeModel, setBladeModel] = useState('')
  const [rubberFhBrand, setRubberFhBrand] = useState('')
  const [rubberFhModel, setRubberFhModel] = useState('')
  const [rubberBhBrand, setRubberBhBrand] = useState('')
  const [rubberBhModel, setRubberBhModel] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  useEffect(() => {
    if (!profile) {
      fetchProfile()
      return
    }
    const p = profile.profile
    setPlayingStyle(p.playing_style || '')
    setSelfLevel(p.self_assessed_level || '')
    const eq = p.equipment_config
    if (eq) {
      setBladeBrand(eq.blade?.brand || '')
      setBladeModel(eq.blade?.model || '')
      setRubberFhBrand(eq.rubber_fh?.brand || '')
      setRubberFhModel(eq.rubber_fh?.model || '')
      setRubberBhBrand(eq.rubber_bh?.brand || '')
      setRubberBhModel(eq.rubber_bh?.model || '')
    }
  }, [profile])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const data: any = {}
      if (playingStyle) data.playing_style = playingStyle
      if (selfLevel) data.self_assessed_level = selfLevel

      // 仅在有输入时组装装备配置
      if (bladeBrand || bladeModel || rubberFhBrand || rubberBhBrand) {
        data.equipment_config = {}
        if (bladeBrand || bladeModel) {
          data.equipment_config.blade = { brand: bladeBrand, model: bladeModel }
        }
        if (rubberFhBrand || rubberFhModel) {
          data.equipment_config.rubber_fh = { brand: rubberFhBrand, model: rubberFhModel }
        }
        if (rubberBhBrand || rubberBhModel) {
          data.equipment_config.rubber_bh = { brand: rubberBhBrand, model: rubberBhModel }
        }
      }

      await updateProfile(data)
      showToast(t('common.saved'))
      setTimeout(() => Taro.navigateBack(), 1000)
    } catch (err: any) {
      showToast(err?.message || t('common.saveFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View className="edit-page">
      {/* 打法选择 */}
      <View className="form-section">
        <View className="section-title">{t('user.playingStyle')}</View>
        <View className="style-grid">
          {PLAYING_STYLES.map((s) => (
            <View
              key={s.value}
              className={`style-chip ${playingStyle === s.value ? 'active' : ''}`}
              onClick={() => setPlayingStyle(s.value)}
            >
              <Text>{t(s.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 自评水平 */}
      <View className="form-section">
        <View className="section-title">{t('user.selfLevel')}</View>
        <View className="level-grid">
          {SELF_LEVELS.map((l) => (
            <View
              key={l.value}
              className={`level-chip ${selfLevel === l.value ? 'active' : ''}`}
              onClick={() => setSelfLevel(l.value)}
            >
              <Text>{t(l.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 装备配置 */}
      <View className="form-section">
        <View className="section-title">{t('user.equipment')}</View>
        <Cell title={t('user.bladeBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={bladeBrand}
            onChange={(val) => setBladeBrand(val)}
          />
        </Cell>
        <Cell title={t('user.bladeModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={bladeModel}
            onChange={(val) => setBladeModel(val)}
          />
        </Cell>
        <Cell title={t('user.rubberFHBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={rubberFhBrand}
            onChange={(val) => setRubberFhBrand(val)}
          />
        </Cell>
        <Cell title={t('user.rubberFHModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={rubberFhModel}
            onChange={(val) => setRubberFhModel(val)}
          />
        </Cell>
        <Cell title={t('user.rubberBHBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={rubberBhBrand}
            onChange={(val) => setRubberBhBrand(val)}
          />
        </Cell>
        <Cell title={t('user.rubberBHModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={rubberBhModel}
            onChange={(val) => setRubberBhModel(val)}
          />
        </Cell>
      </View>

      <Button
        type="primary"
        block
        loading={submitting}
        onClick={handleSubmit}
        className="submit-btn"
      >
        {t('common.save')}
      </Button>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
