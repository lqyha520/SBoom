import type { RequestScope } from './latest-request'

export type PageTicket = (() => boolean) & RequestScope

/** 页面读取共用的可见性、账号和取消边界；写操作仍由服务端保证幂等。 */
export function usePageLifecycle(owner: () => unknown) {
  let active = false, revision = 0
  const cancellations = new Set<() => void>()
  function invalidate() { revision++; for (const cancel of cancellations) cancel(); cancellations.clear() }
  function ticket(): PageTicket {
    const version = revision, account = owner()
    const valid = () => active && version === revision && account === owner()
    return Object.assign(valid, { onCancel(cancel: () => void) {
      if (!valid()) { cancel(); return () => {} }
      cancellations.add(cancel)
      return () => { cancellations.delete(cancel) }
    } })
  }
  return { get active() { return active }, show() { active = true }, leave() { active = false; invalidate() }, invalidate, ticket,
    begin() { invalidate(); return ticket() } }
}

/** 只在离开页面时跨一次渲染线程，避免 onPageScroll 逐帧回传。 */
export function captureScroll(save: (top: number) => void) {
  try { uni.createSelectorQuery().selectViewport().scrollOffset(result => { if (result && !Array.isArray(result) && typeof result.scrollTop === 'number') save(result.scrollTop) }).exec() }
  catch { /* 查询不可用时继续沿用上次位置。 */ }
}
