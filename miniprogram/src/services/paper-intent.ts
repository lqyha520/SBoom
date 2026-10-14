import type { PrintEdition } from '../types'

type PaperIntent = { paperId: string; action: 'download' | 'favorite'; edition: PrintEdition['kind'] }
let pending: (PaperIntent & { expires: number; owner: string | null }) | null = null

/** Only an explicit guest action can create an intent; it never comes from a shared URL. */
export function rememberPaperIntent(intent: PaperIntent) {
  pending = { ...intent, expires: Date.now() + 10 * 60_000, owner: null }
}
export function bindPaperIntent(owner: string) {
  if (pending && pending.owner === null) pending.owner = owner
}
export function clearPaperIntent() { pending = null }
export function takePaperIntent(paperId: string, owner: string): PaperIntent | null {
  if (!pending) return null
  if (pending.expires <= Date.now() || pending.owner !== owner) { pending = null; return null }
  if (pending.paperId !== paperId) return null
  const { action, edition } = pending
  pending = null
  return { paperId, action, edition }
}
