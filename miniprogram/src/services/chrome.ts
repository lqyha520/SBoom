/**
 * 自绘导航栏（globalStyle.navigationStyle = custom）的垂直几何。
 * 全站只有这一处计算：状态栏内边距 inset 与整条栏高 height（对齐微信胶囊，
 * 避免标题/返回按钮被系统胶囊或状态栏压住）。
 */
export function chromeBar(): { inset: number; height: number } {
  let inset = 0
  let height = 52
  // #ifdef MP-WEIXIN
  const windowInfo = uni.getWindowInfo()
  const capsule = uni.getMenuButtonBoundingClientRect()
  inset = windowInfo.statusBarHeight || 20
  // 胶囊 bottom 缺失时用 top + height 兜底，否则会算出 NaN 把整条栏压塌。
  const bottom = capsule.bottom || (capsule.top || 0) + (capsule.height || 0)
  height = Math.max(inset + 44, bottom + 8)
  // #endif
  return { inset, height }
}
