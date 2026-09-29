import type { PaperSummary } from '../types'

/** 服务端会带回详情字段，只比较并更新列表已有字段，保留未变化行的 props 引用。 */
export function reconcileRows(previous: PaperSummary[], incoming: PaperSummary[]) {
  const byId = new Map(incoming.map(item => [item.id, item]))
  return previous.map(old => {
    const fresh = byId.get(old.id)
    if (!fresh) return old
    const keys = Object.keys(old) as (keyof PaperSummary)[]
    if (keys.every(key => JSON.stringify(old[key]) === JSON.stringify(fresh[key]))) return old
    return { ...old, ...Object.fromEntries(keys.map(key => [key, fresh[key]])) }
  })
}
