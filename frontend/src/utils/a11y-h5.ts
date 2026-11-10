/**
 * H5 端无障碍运行时补丁（FS8-7 axe 扫描修复）
 *
 * 1. scrollable-region-focusable（WCAG 2.1）：Taro H5 运行时生成的页面容器
 *    `.taro_page`（overflow 可滚动）与业务横向滚动条 `.filter-bar`（scoring
 *    match-list 日期筛选）默认不带 tabindex，键盘用户无法聚焦滚动。
 *    框架容器无法在 JSX 中声明属性，故以 MutationObserver 动态补
 *    tabindex="0"（axe 该规则认可 tabindex 为可聚焦修复）。
 *
 * 2. image-alt：Taro H5 taro-image-core 将 React `alt` prop 落在宿主
 *    custom element 上，不转发到内部 <img>（探针实证）。此处在 DOM
 *    变更时将宿主 alt 同步到内部 img（幂等；alt 后置变化——如异步加载
 *    的用户昵称——由 attribute 监听覆盖）。
 *
 * weapp 端 Taro 编译期注入 TARO_ENV 常量，'h5' 分支被 tree-shake；
 * jest 环境 TARO_ENV 未注入时同走早退。
 */
const FOCUSABLE_SCROLLABLE_SELECTOR = '.taro_page, .filter-bar'

function patchScrollable(el: Element): void {
  if (!el.hasAttribute('tabindex')) {
    el.setAttribute('tabindex', '0')
  }
}

function patchImageAlt(host: Element): void {
  if (!host.matches?.('taro-image-core')) return
  const alt = host.getAttribute('alt')
  const img = host.querySelector('img')
  if (alt !== null && img && img.getAttribute('alt') !== alt) {
    img.setAttribute('alt', alt)
  }
}

function patchNode(node: Element): void {
  if (node instanceof HTMLElement) {
    // 内部 <img> 由 custom element 在宿主挂载后渲染——img 添加事件须回溯宿主
    const parent = node.parentElement
    if (parent?.matches?.('taro-image-core')) {
      patchImageAlt(parent)
    }
    patchImageAlt(node)
    if (node.matches?.(FOCUSABLE_SCROLLABLE_SELECTOR)) {
      patchScrollable(node)
    }
    node.querySelectorAll?.(FOCUSABLE_SCROLLABLE_SELECTOR).forEach(patchScrollable)
    node.querySelectorAll?.('taro-image-core').forEach(patchImageAlt)
  }
}

let installed = false

export function setupA11yH5Patches(): void {
  if (process.env.TARO_ENV !== 'h5') return
  if (installed) return
  if (typeof document === 'undefined' || typeof MutationObserver === 'undefined') return

  installed = true

  patchNode(document.body)

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'attributes') {
        // taro-image-core 宿主 alt 后置变化（异步昵称等）
        if (mutation.target instanceof Element) {
          patchImageAlt(mutation.target)
        }
        continue
      }
      mutation.addedNodes.forEach((node) => {
        if (node instanceof HTMLElement) patchNode(node)
      })
    }
  })

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['alt'],
  })
}
