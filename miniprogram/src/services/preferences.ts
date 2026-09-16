/** Search preferences are local, bounded and isolated by consumer account. */
export interface Preferences { grade: string; subject: string; history: string[] }
export function cleanPreferences(value: unknown): Preferences {
  const input = value && typeof value === 'object' ? value as Partial<Preferences> : {}
  return {
    grade: typeof input.grade === 'string' ? input.grade.slice(0, 80) : '',
    subject: typeof input.subject === 'string' ? input.subject.slice(0, 80) : '',
    history: Array.isArray(input.history) ? [...new Set(input.history.filter((item): item is string => typeof item === 'string').map(item => item.trim().slice(0, 120)).filter(Boolean))].slice(0, 12) : [],
  }
}
export function rememberSearch(value: Preferences, query: string): Preferences {
  return cleanPreferences({ ...value, history: [query, ...value.history] })
}
export function readPreferences(owner: string): Preferences {
  try { return owner ? cleanPreferences(uni.getStorageSync('lc-reader-preferences:' + owner)) : cleanPreferences(null) }
  catch { return cleanPreferences(null) }
}
export function writePreferences(owner: string, value: Preferences) {
  if (!owner) return
  try { uni.setStorageSync('lc-reader-preferences:' + owner, cleanPreferences(value)) } catch { /* Searches remain available in the current page. */ }
}
