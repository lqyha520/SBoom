const KEY = 'lc-reading-position-v1'
interface Position { key: string; page: number }
let cached: Position[] | undefined
let writing = false, queued = false
function persist() {
  if (writing) { queued = true; return }
  writing = true
  const complete = () => { writing = false; if (queued) { queued = false; persist() } }
  try { uni.setStorage({ key: KEY, data: entries().map(item => ({ ...item })), complete }) }
  catch { complete() }
}
function entries(): Position[] {
  if (cached) return cached
  try {
    const saved: unknown = uni.getStorageSync(KEY)
    if (!Array.isArray(saved)) return []
    return cached = saved.filter((item): item is Position => !!item && typeof item.key === 'string' && Number.isInteger(item.page) && item.page >= 0).slice(0, 50)
  } catch { return [] }
}
const identity = (owner: string, paper: string, release: number) => JSON.stringify([owner || 'guest', paper, release])
export function readPosition(owner: string, paper: string, release: number, count: number) {
  const saved = entries().find(item => item.key === identity(owner, paper, release))
  return Math.max(0, Math.min(saved?.page || 0, count - 1))
}
export function rememberPosition(owner: string, paper: string, release: number, page: number) {
  if (!Number.isInteger(page) || page < 0) return
  const key = identity(owner, paper, release)
  cached = [{ key, page }, ...entries().filter(item => item.key !== key)].slice(0, 50)
  persist()
}
