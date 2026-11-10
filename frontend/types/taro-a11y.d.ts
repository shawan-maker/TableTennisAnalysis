/**
 * Taro 组件类型增强（FS8-7 无障碍）
 *
 * Taro H5 taro-image-core 将 `alt` prop 落在宿主 custom element 上，
 * 由 src/utils/a11y-h5.ts 运行时同步至内部 <img>（Taro 4.3.2 不转发）。
 * weapp 端 Image 无 alt 属性（微信原生 image 组件不支持），属性被忽略。
 * 此处仅为 alt prop 提供 TS 声明，避免调用点 as any 逃逸。
 */
import '@tarojs/components'

declare module '@tarojs/components' {
  interface ImageProps {
    /** 图片替代文本（H5 端由 a11y-h5 运行时同步到内部 img；weapp 忽略） */
    alt?: string
  }
}
