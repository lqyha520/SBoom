import { openDB } from 'idb'
import { clearWorkspace } from './persistence'

export interface StorageUsage { usage: number; quota: number; persisted: boolean }
export async function storageUsage(requestPersistence = false): Promise<StorageUsage | null> {
  if (!navigator.storage?.estimate) return null
  try {
    let persisted = await navigator.storage.persisted?.() || false
    if (requestPersistence && !persisted) persisted = await navigator.storage.persist?.() || false
    const estimate = await navigator.storage.estimate()
    return { usage: estimate.usage || 0, quota: estimate.quota || 0, persisted }
  } catch { return null }
}

export async function clearAccountData(owner: string): Promise<void> {
  localStorage.setItem('lc_purge:' + owner, String(Date.now()))
  await clearWorkspace(owner)
  const prefix = `lc_u${owner}_`
  const db = await openDB('lc-worksheet-images', 1, { upgrade(value) { value.createObjectStore('images') } })
  try {
    const tx = db.transaction('images', 'readwrite')
    let cursor = await tx.store.openCursor()
    while (cursor) {
      if (String(cursor.key).startsWith(prefix)) await cursor.delete()
      cursor = await cursor.continue()
    }
    await tx.done
  } finally { db.close() }
  for (const key of Object.keys(localStorage)) if (key.startsWith(prefix)) localStorage.removeItem(key)
  if (localStorage.getItem('lc_legacy_owner') === owner) {
    for (const key of ['lc_custom_types', 'lc_template', 'lc_custom_template', 'lc_paper_style', 'lc_my_templates', 'lc_paper_bg', 'lc_paper_kid', 'lc_legacy_owner']) localStorage.removeItem(key)
  }
  sessionStorage.removeItem('lc_draft_session:' + owner)
}
