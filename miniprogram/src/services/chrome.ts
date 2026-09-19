/**
 * 自绘导航栏（globalStyle.navigationStyle = custom）的垂直几何。
 * 全站只有这一处计算，避免各页自己算导致返回按钮位置/栏高不一致：
 *  - inset：状态栏内边距（顶部安全区），用于 padding-top 或按钮的 top。
 *  - height：整条栏的**总高**（含状态栏），即「状态栏 + 44px 内容行」与
 *    「胶囊下方 8px」取较大值。用作占位高度时直接用它；若元素已经用
 *    padding-top 顶出状态栏（border-box），也直接用它，**不要再加 inset**。
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
