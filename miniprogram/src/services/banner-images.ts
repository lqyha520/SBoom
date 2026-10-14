import type { FileHandle } from './file-pool'

interface BannerImage { id: string; image_url: string | null }
interface HeldImage { source: string; handle: FileHandle; path?: string }

/** Track the URL as well as the id: replacing an image keeps its Banner id. */
export function createBannerImages(acquire: (url: string) => FileHandle, display: (id: string, path: string) => void) {
  const held = new Map<string, HeldImage>()
  function remove(id: string, entry: HeldImage) {
    held.delete(id)
    entry.handle.release()
    display(id, '')
  }
  return {
    sync(all: BannerImage[], current = 0) {
      const banners = all.length ? [all[current % all.length]!, all[(current + 1) % all.length]!] : []
      const sources = new Map(banners.map(banner => [banner.id, banner.image_url]))
      for (const [id, entry] of held) {
        if (sources.get(id) !== entry.source) remove(id, entry)
      }
      for (const banner of banners) {
        if (!banner.image_url || held.has(banner.id)) continue
        const entry: HeldImage = { source: banner.image_url, handle: acquire(banner.image_url) }
        held.set(banner.id, entry)
        void entry.handle.ready.then(path => {
          // An unrelated refresh must not discard a still-pending image.
          // A late result from a replaced image must never reappear.
          if (held.get(banner.id) !== entry) return
          entry.path = path
          display(banner.id, path)
        }).catch(() => { if (held.get(banner.id) === entry) remove(banner.id, entry) })
      }
    },
    fail(id: string, path: string) {
      const entry = held.get(id)
      if (entry && entry.path === path) {
        entry.handle.invalidate()
        remove(id, entry)
      }
    },
    clear() { for (const [id, entry] of held) remove(id, entry) },
  }
}
