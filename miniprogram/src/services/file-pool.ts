export interface FileHandle {
  ready: Promise<string>
  release(): void
  invalidate(): void
}

interface Entry {
  ready: Promise<string>
  users: number
  active: boolean
  file?: string
  progress?: number
  listeners: Set<(percent: number) => void>
}

// Share active downloads, but keep no files after their last consumer leaves.
export function createFilePool(download: (key: string, progress: (percent: number) => void) => Promise<string>, dispose: (file: string) => void) {
  const entries = new Map<string, Entry>()

  function discard(key: string, entry: Entry) {
    if (entries.get(key) === entry) entries.delete(key)
    entry.active = false
    entry.listeners.clear()
    if (entry.file) { dispose(entry.file); entry.file = undefined }
  }

  return {
    acquire(key: string, progress?: (percent: number) => void): FileHandle {
      let entry = entries.get(key)
      if (!entry) {
        const created: Entry = { ready: Promise.resolve(''), users: 0, active: true, listeners: new Set() }
        entries.set(key, created)
        created.ready = Promise.resolve().then(() => {
          if (!created.active) throw new Error('File request expired')
          return download(key, percent => {
            if (!created.active) return
            created.progress = Math.max(0, Math.min(100, percent))
            created.listeners.forEach(listener => listener(created.progress!))
          })
        }).then(file => {
          if (!created.active) { dispose(file); throw new Error('File request expired') }
          created.file = file
          return file
        }).catch(error => { discard(key, created); throw error })
        entry = created
      }
      const held = entry
      if (progress) { held.listeners.add(progress); if (held.progress !== undefined) progress(held.progress) }
      held.users++
      let released = false
      return {
        ready: held.ready,
        release() {
          if (released) return
          released = true
          if (progress) held.listeners.delete(progress)
          if (--held.users === 0) discard(key, held)
        },
        invalidate() { discard(key, held) },
      }
    },
    clear() { for (const [key, entry] of entries) discard(key, entry) },
  }
}
