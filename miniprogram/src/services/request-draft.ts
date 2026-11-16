export interface RequestDraft { title: string; grade: string; subject: string; details: string }
const key = (owner: string) => 'lc-resource-draft-v1:' + owner
const ttl = 7 * 86400_000
export function cleanRequestDraft(value: unknown): RequestDraft {
  const data = value && typeof value === 'object' ? value as Partial<RequestDraft> : {}
  const text = (name: keyof RequestDraft, max: number) => typeof data[name] === 'string' ? data[name].slice(0, max) : ''
  return { title: text('title', 120), grade: text('grade', 80), subject: text('subject', 80), details: text('details', 1000) }
}
/** 需求与反馈共用七天保留、账号隔离和存储失败处理。 */
export function readLocalDraft<T>(storageKey: string, clean: (value: unknown) => T): T | null {
  try {
    const saved = uni.getStorageSync(storageKey)
    if (!saved || typeof saved.updatedAt !== 'number' || !Number.isFinite(saved.updatedAt)) return null
    if (Date.now() - saved.updatedAt > ttl || saved.updatedAt > Date.now() + 60000) {
      uni.removeStorageSync(storageKey); return null
    }
    return clean(saved)
  } catch { return null }
}
export function writeLocalDraft(storageKey: string, draft: object, hasContent: boolean): boolean {
  try {
    if (!hasContent) uni.removeStorageSync(storageKey)
    else uni.setStorageSync(storageKey, { ...draft, updatedAt: Date.now() })
    return true
  } catch { return false }
}
export function readRequestDraft(owner: string): RequestDraft | null { return owner ? readLocalDraft(key(owner), cleanRequestDraft) : null }
export function writeRequestDraft(owner: string, value: RequestDraft): boolean {
  const draft = cleanRequestDraft(value)
  return !!owner && writeLocalDraft(key(owner), draft, Object.values(draft).some(value => value.trim()))
}
