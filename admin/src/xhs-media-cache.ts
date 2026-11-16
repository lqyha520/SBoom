import { openDB } from 'idb'

export interface PublicationMedia {
  id: string; asset_id: string; name: string; media_type: string; size_bytes: number; last_modified: number
}
const openCache = () => openDB('lc-xhs-publication-media', 1, { upgrade(db) { db.createObjectStore('files') } })
export const LOCAL_MEDIA_BUDGET = 256 * 1024 * 1024
interface CachedFile { blob: Blob; savedAt: number }

export async function cachePublicationFile(owner: number, reference: PublicationMedia, file: File, protectedIds: string[]) {
  const db = await openCache()
  try {
    const prefix = `${owner}:`, key = prefix + reference.id
    const tx = db.transaction('files', 'readwrite')
    void tx.done.catch(() => {}) // 写入失败时由调用方提示，避免事务产生未处理的拒绝。
    const entries: { key: string; bytes: number; savedAt: number }[] = []
    let cursor = await tx.store.openCursor(IDBKeyRange.bound(prefix, prefix + '\uffff'))
    while (cursor) {
      const value = cursor.value as CachedFile
      entries.push({ key: String(cursor.key), bytes: value.blob.size, savedAt: value.savedAt })
      cursor = await cursor.continue()
    }
    let bytes = entries.filter(item => item.key !== key).reduce((total, item) => total + item.bytes, file.size)
    const protectedKeys = new Set(protectedIds.map(id => prefix + id))
    const removable = entries.filter(item => item.key !== key && !protectedKeys.has(item.key)).sort((a, b) => a.savedAt - b.savedAt)
    if (bytes - removable.reduce((total, item) => total + item.bytes, 0) > LOCAL_MEDIA_BUDGET) {
      await tx.done
      throw new Error('本机配图空间不足，请下载备份或改用素材库')
    }
    for (const entry of removable) {
      if (bytes <= LOCAL_MEDIA_BUDGET) break
      await tx.store.delete(entry.key); bytes -= entry.bytes
    }
    await tx.store.put({ blob: file, savedAt: Date.now() } satisfies CachedFile, key)
    await tx.done
  } finally { db.close() }
}

export async function readPublicationFile(owner: number, reference: PublicationMedia): Promise<File | null> {
  const db = await openCache()
  try {
    const value = await db.get('files', `${owner}:${reference.id}`) as CachedFile | undefined
    if (!value?.blob || value.blob.size !== reference.size_bytes || value.blob.type !== reference.media_type) return null
    return new File([value.blob], reference.name, { type: reference.media_type, lastModified: reference.last_modified })
  } finally { db.close() }
}
