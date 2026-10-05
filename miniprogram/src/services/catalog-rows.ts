import type { PaperSummary } from '../types'

/** 服务端会带回详情字段，只比较并更新列表已有字段，保留未变化行的 props 引用。 */
export function reconcileRows(previous: PaperSummary[], incoming: PaperSummary[]) {
  const byId = new Map(incoming.map(item => [item.id, item]))
  return previous.map(old => {
    const fresh = byId.get(old.id)
    if (!fresh) return old
    const keys = Object.keys(old) as (keyof PaperSummary)[]
    // Window rights do not carry the activity timestamp of the originating list.
    const value = (key: keyof PaperSummary) => key === 'activity_at' && !Object.prototype.hasOwnProperty.call(fresh, key) ? old[key] : fresh[key]
    if (keys.every(key => JSON.stringify(old[key]) === JSON.stringify(value(key)))) return old
    return { ...old, ...Object.fromEntries(keys.map(key => [key, value(key)])) }
  })
}
