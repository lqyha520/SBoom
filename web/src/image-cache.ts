import { openDB } from 'idb'
import { imageBlob, type WorksheetImage } from './image-generation'

export const IMAGE_CACHE_BUDGET = 256 * 1024 * 1024
export const openImageCache = async () => openDB('lc-worksheet-images', 1, { upgrade(db) { db.createObjectStore('images') } })
export interface ImageCacheUsage { bytes: number; count: number; limit: number }
type CachedImage = WorksheetImage & { cachedAt?: number }

// 同一账号的读取、清理和写入处于一个事务，多窗口并发也不能越过容量预算。
export async function manageImageCache(storageKey: string, protectedIds: string[], options: {
  image?: WorksheetImage; clearHistory?: boolean; prune?: boolean; limit?: number; active?: () => boolean
} = {}): Promise<ImageCacheUsage & { stored: boolean; removed: number }> {
  const prefix = storageKey + ':', limit = options.limit ?? IMAGE_CACHE_BUDGET
  const db = await openImageCache()
  try {
    const tx = db.transaction('images', 'readwrite')
    void tx.done.catch(() => {}) // 请求失败会同时拒绝事务，交由调用方显示缓存失败提示。
    const entries: { key: string; bytes: number; age: number }[] = []
    let cursor = await tx.store.openCursor(IDBKeyRange.bound(prefix, prefix + '\uffff'))
    while (cursor) {
      const value = cursor.value as CachedImage
      let bytes = 0
      try { bytes = imageBlob(value).size } catch { /* 坏缓存仍可清理，恢复时回源。 */ }
      entries.push({ key: String(cursor.key), bytes, age: value.cachedAt || 0 })
      cursor = await cursor.continue()
    }
    const protectedKeys = new Set(protectedIds.map(id => prefix + id))
    const image = options.image, key = image ? prefix + image.request_id : ''
    const old = entries.find(entry => entry.key === key)
    let bytes = entries.reduce((sum, entry) => sum + entry.bytes, 0), count = entries.length, removed = 0, stored = false
    const size = image ? imageBlob(image).size : 0
    const candidates = entries.filter(entry => !protectedKeys.has(entry.key) && entry.key !== key).sort((a, b) => a.age - b.age || a.key.localeCompare(b.key))
    const active = options.active?.() ?? true
    const canFit = bytes - (old?.bytes || 0) + size - candidates.reduce((sum, entry) => sum + entry.bytes, 0) <= limit
    if (active && (image || options.prune || options.clearHistory) && (!image || canFit || options.clearHistory)) {
      for (const entry of candidates) {
        if (!options.clearHistory && bytes - (old?.bytes || 0) + size <= limit) break
        await tx.store.delete(entry.key); bytes -= entry.bytes; count--; removed++
      }
      if (image && bytes - (old?.bytes || 0) + size <= limit && (options.active?.() ?? true)) {
        await tx.store.put({ ...image, cachedAt: Date.now() } satisfies CachedImage, key)
        bytes += size - (old?.bytes || 0); if (!old) count++; stored = true
      }
    }
    await tx.done
    return { bytes, count, limit, stored, removed }
  } finally { db.close() }
}
