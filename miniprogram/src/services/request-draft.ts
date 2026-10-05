export interface RequestDraft { title: string; grade: string; subject: string; details: string }
const key = (owner: string) => 'lc-resource-draft-v1:' + owner
const ttl = 7 * 86400_000
export function cleanRequestDraft(value: unknown): RequestDraft {
  const data = value && typeof value === 'object' ? value as Partial<RequestDraft> : {}
  const text = (name: keyof RequestDraft, max: number) => typeof data[name] === 'string' ? data[name].slice(0, max) : ''
  return { title: text('title', 120), grade: text('grade', 80), subject: text('subject', 80), details: text('details', 1000) }
}
export function readRequestDraft(owner: string): RequestDraft | null {
  if (!owner) return null
  try {
    const saved = uni.getStorageSync(key(owner))
    if (!saved || typeof saved.updatedAt !== 'number') return null
    if (Date.now() - saved.updatedAt > ttl || saved.updatedAt > Date.now() + 60000) {
      uni.removeStorageSync(key(owner)); return null
    }
    return cleanRequestDraft(saved)
  } catch { return null }
}
export function writeRequestDraft(owner: string, value: RequestDraft): boolean {
  if (!owner) return false
  try {
    const draft = cleanRequestDraft(value)
    if (!Object.values(draft).some(value => value.trim())) uni.removeStorageSync(key(owner))
    else uni.setStorageSync(key(owner), { ...draft, updatedAt: Date.now() })
    return true
  } catch { return false }
}
