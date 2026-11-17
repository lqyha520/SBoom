import type { ApiSchemas } from '../../../shared/api-schema'
import { ApiError, request } from '../api'
import { randomId } from '../../../shared/webcrypto'
import { cloudGames as games, gameKey, validSave, type CloudGameId as GameId } from './catalog'

type Save = ApiSchemas['GameSave']
interface Base { revision: number; raw: string | null }
export interface GameConflict { id: GameId; remote: Save }
interface Transport { list: () => Promise<Save[]>; put: (id: GameId, body: ApiSchemas['GameSaveInput']) => Promise<Save> }
const rawOf = (value: unknown) => JSON.stringify(value)
// 后端 JSON 字段顺序可能不同，比较内容时使用递归排序。
export function sameSave(a: string | null, b: string | null): boolean {
  const sort = (value: unknown): unknown => Array.isArray(value) ? value.map(sort) : value && typeof value === 'object'
    ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => [key, sort(value)])) : value
  try { return a === b || a !== null && b !== null && JSON.stringify(sort(JSON.parse(a))) === JSON.stringify(sort(JSON.parse(b))) } catch { return false }
}

export class GameCloud {
  status = '正在读取云端进度'
  conflicts: GameConflict[] = []
  error = ''
  ready = false
  disposed = false
  private busy = new Set<GameId>()
  private timers = new Map<GameId, ReturnType<typeof setTimeout>>()
  private bases = new Map<GameId, Base>()
  private checked = new Set<GameId>()
  private failures = new Map<GameId, string>()
  private listError = ''
  private loading = false
  private refreshQueued = false
  private controller = new AbortController()
  private transport: Transport
  constructor(public owner: string, private changed: (restored?: GameId) => void, transport?: Transport, private validate = validSave) {
    this.transport = transport || {
      list: async () => (await request<ApiSchemas['GameSaves']>('/api/v1/me/games', { signal: this.controller.signal }, 8000)).items,
      put: (id, body) => request<Save>('/api/v1/me/games/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: this.controller.signal }, 8000),
    }
  }
  private base(id: GameId): Base {
    if (this.bases.has(id)) return this.bases.get(id)!
    try {
      const value = JSON.parse(localStorage.getItem(gameKey(id, this.owner) + ':cloud') || 'null')
      if (value && Number.isSafeInteger(value.revision) && value.revision >= 0 && (value.raw === null || typeof value.raw === 'string')) return value
    } catch { /* 缺少基线时按两个独立存档处理，不覆盖。 */ }
    return { revision: 0, raw: null }
  }
  private remember(id: GameId, value: Save) {
    const base = { revision: value.revision, raw: rawOf(value.progress) }
    localStorage.setItem(gameKey(id, this.owner) + ':cloud', JSON.stringify(base))
    this.bases.set(id, base)
  }
  private notify(restored?: GameId) {
    if (this.disposed) return
    this.error = this.listError || [...this.failures].map(([id, message]) => `${games.find(game => game.id === id)?.title || id}：${message}`).join('；')
    this.status = this.loading ? '正在核对云端进度' : this.listError ? '本机进度已保留，云同步待重试'
      : this.failures.size ? `${this.failures.size} 个游戏暂未同步，其余进度可继续同步`
      : this.conflicts.length ? '有进度冲突，请选择存档' : this.busy.size ? '正在同步进度'
      : this.timers.size ? '进度已存本机，等待同步' : '云端进度已同步'
    this.changed(restored)
  }
  private canSync(id: GameId) {
    return !this.disposed && this.ready && this.checked.has(id) && !this.failures.has(id) && !this.conflicts.some(item => item.id === id)
  }
  private async reconcile(id: GameId, server?: Save) {
    try {
      this.conflicts = this.conflicts.filter(conflict => conflict.id !== id)
      if (server && !await this.validate(id, rawOf(server.progress))) throw new Error('云端存档无法读取，本机进度已保留')
      if (this.disposed) return
      const key = gameKey(id, this.owner), local = localStorage.getItem(key), base = this.base(id)
      if (!server) this.bases.set(id, { revision: 0, raw: null })
      else {
        const cloudRaw = rawOf(server.progress)
        if (sameSave(local, cloudRaw)) this.remember(id, server)
        else if (!local || sameSave(local, base.raw)) {
          localStorage.setItem(key, cloudRaw)
          localStorage.setItem(key + ':played', String(server.updated_at * 1000))
          this.remember(id, server); this.notify(id)
        } else if (sameSave(cloudRaw, base.raw)) this.remember(id, server)
        else this.conflicts.push({ id, remote: server })
      }
      this.checked.add(id)
      this.failures.delete(id)
    } catch (error) {
      if (!this.disposed) this.failures.set(id, error instanceof Error ? error.message : '暂时无法同步')
    }
  }
  async refresh() {
    if (this.disposed || this.loading) return
    if (this.busy.size) { this.refreshQueued = true; return }
    this.refreshQueued = false
    this.timers.forEach(clearTimeout); this.timers.clear()
    this.loading = true; this.ready = false; this.listError = ''; this.checked.clear(); this.notify()
    try {
      const remote = await this.transport.list()
      if (this.disposed) return
      // 每个游戏独立校验和恢复，模块加载失败或损坏存档不阻断其他游戏。
      await Promise.all(games.map(game => this.reconcile(game.id, remote.find(item => item.game_id === game.id))))
      if (this.disposed) return
      this.ready = true
      for (const game of games) {
        if (!this.canSync(game.id)) continue
        try {
          if (!sameSave(localStorage.getItem(gameKey(game.id, this.owner)), this.base(game.id).raw)) this.schedule(game.id)
        } catch (error) { this.failures.set(game.id, error instanceof Error ? error.message : '本机存档无法读取') }
      }
    } catch (error) { if (!this.disposed) this.listError = error instanceof Error ? error.message : '暂时无法同步' }
    finally { this.loading = false; this.notify() }
  }
  schedule(id: GameId) {
    if (!this.canSync(id)) return
    clearTimeout(this.timers.get(id))
    this.timers.set(id, setTimeout(() => { this.timers.delete(id); void this.flush(id) }, 1800))
    this.notify()
  }
  async flush(id: GameId) {
    clearTimeout(this.timers.get(id)); this.timers.delete(id)
    if (!this.canSync(id) || this.busy.has(id)) return
    this.busy.add(id); this.notify()
    let conflict = false
    try {
      const raw = localStorage.getItem(gameKey(id, this.owner)), base = this.base(id)
      if (!raw || sameSave(raw, base.raw)) return
      if (!await this.validate(id, raw)) throw new Error('本机存档无法同步，请重新打开游戏核对')
      if (this.disposed) return
      const saved = await this.transport.put(id, { progress: JSON.parse(raw), revision: base.revision, mutation_id: randomId() })
      if (this.disposed) return
      this.remember(id, saved); this.failures.delete(id)
      if (!sameSave(localStorage.getItem(gameKey(id, this.owner)), raw)) this.schedule(id)
    } catch (error) {
      if (!this.disposed) {
        conflict = error instanceof ApiError && error.status === 409
        this.failures.set(id, error instanceof Error ? error.message : '暂时无法同步')
        this.checked.delete(id)
      }
    } finally {
      this.busy.delete(id); this.notify()
      if (conflict) this.refreshQueued = true
      if (this.refreshQueued && !this.busy.size) await this.refresh()
    }
  }
  async resolve(id: GameId, use: 'local' | 'cloud') {
    const conflict = this.conflicts.find(item => item.id === id)
    if (!conflict || this.disposed || this.loading || this.busy.has(id)) return
    try {
      if (use === 'cloud') {
        localStorage.setItem(gameKey(id, this.owner) + ':backup', localStorage.getItem(gameKey(id, this.owner)) || '')
        localStorage.setItem(gameKey(id, this.owner), rawOf(conflict.remote.progress))
        localStorage.setItem(gameKey(id, this.owner) + ':played', String(conflict.remote.updated_at * 1000))
      }
      this.remember(id, conflict.remote)
      this.failures.delete(id); this.checked.add(id)
      this.conflicts = this.conflicts.filter(item => item.id !== id)
      this.notify(use === 'cloud' ? id : undefined)
      if (use === 'local') await this.flush(id)
    } catch { this.failures.set(id, '本机空间不足，尚未更换存档'); this.notify() }
  }
  dispose() { this.disposed = true; this.controller.abort(); this.timers.forEach(clearTimeout); this.timers.clear() }
}
