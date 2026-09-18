/**
 * 交互体验工具。
 *
 * 只保留微信端真正可用的能力：浏览器专用工具（new Image()、IntersectionObserver、
 * URLSearchParams、DOM 节点操作）在小程序里没有对应对象，留着会被误调用且白占包体，
 * 已随 2026-09-18 的死代码清理一并移除。
 */

/** 防抖：合并高频调用，只执行最后一次。目录搜索框逐字输入时用。 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null

  return function (this: any, ...args: Parameters<T>) {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => {
      func.apply(this, args)
    }, wait)
  }
}

/** 震动强度，与微信 wx.vibrateShort 的 type 取值一致（需基础库 2.13.0+）。 */
export type VibrateType = 'heavy' | 'medium' | 'light'

/** 轻震动反馈：滑动操作、收藏等即时交互用。非微信端为空实现。 */
export function vibrate(type: VibrateType = 'light'): void {
  // #ifdef MP-WEIXIN
  uni.vibrateShort?.({ type })
  // #endif
}
