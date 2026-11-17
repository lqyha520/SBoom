import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import examples from '../../../tests/fixtures/game-progress.json'
import { GameCloud, sameSave } from '../games/cloud-saves'
import { ApiError } from '../api'
import { gameKey, validSave } from '../games/catalog'
import { localProgress, writeGameSave } from '../games/game-storage'
import { newRocket } from '../games/rocket-math'
import { newMaze } from '../games/robot-maze'
import type { ApiSchemas } from '../../../shared/api-schema'

it('前后端共用的真实存档样本均可被游戏恢复', async () => {
  for (const [game, progress] of Object.entries(examples)) {
    expect(await validSave(game as Save['game_id'], JSON.stringify(progress)), game).toBe(true)
  }
})

type Save = ApiSchemas['GameSave']
const id = 'rocket-math' as const, key = gameKey(id, '7')
const snapshot = (n: number): Save => ({ game_id: id, revision: n, mutation_id: `mutation-${n}`, updated_at: n, progress: { version: 1, round: n } })
let clouds: GameCloud[] = []
beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { clouds.forEach(cloud => cloud.dispose()); clouds = []; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
function fixture(initial?: Save) {
  let remote = initial
  const list = vi.fn(async () => remote ? [remote] : [])
  const put = vi.fn(async (_id, body: ApiSchemas['GameSaveInput']) => {
    if (body.revision !== (remote?.revision || 0)) throw new ApiError('conflict', 409)
    remote = { ...body, game_id: id, revision: body.revision + 1, updated_at: 10 }; return remote
  })
  const changed = vi.fn()
  const cloud = new GameCloud('7', changed, { list, put }, async () => true)
  clouds.push(cloud)
  return { cloud, list, put, changed, set: (value: Save) => { remote = value } }
}

it('新设备先恢复云端；游客与其他账号的本机存档保持独立', async () => {
  const f = fixture(snapshot(2))
  localStorage.setItem(gameKey(id), 'guest'); localStorage.setItem(gameKey(id, '8'), 'other')
  await f.cloud.refresh()
  expect(JSON.parse(localStorage.getItem(key)!)).toEqual(snapshot(2).progress)
  expect(f.changed).toHaveBeenCalledWith(id); expect(f.put).not.toHaveBeenCalled()
  expect(localStorage.getItem(gameKey(id))).toBe('guest'); expect(localStorage.getItem(gameKey(id, '8'))).toBe('other')
})
it('本机新进度上传；另一设备同时更新时保留两份，由用户选择', async () => {
  const f = fixture(snapshot(1)); await f.cloud.refresh()
  localStorage.setItem(key, JSON.stringify({ version: 1, round: 3 }))
  f.set(snapshot(2)); await f.cloud.flush(id)
  expect(f.cloud.conflicts).toHaveLength(1)
  expect(JSON.parse(localStorage.getItem(key)!).round).toBe(3)
  await f.cloud.resolve(id, 'local')
  expect(f.put).toHaveBeenLastCalledWith(id, expect.objectContaining({ revision: 2, progress: { version: 1, round: 3 } }))
  expect(f.cloud.conflicts).toHaveLength(0)
})
it('选择云端会备份原本机进度；同内容不同字段顺序不会冲突', async () => {
  const f = fixture(snapshot(2)); localStorage.setItem(key, JSON.stringify({ version: 1, round: 3 }))
  await f.cloud.refresh(); await f.cloud.resolve(id, 'cloud')
  expect(JSON.parse(localStorage.getItem(key + ':backup')!).round).toBe(3)
  expect(JSON.parse(localStorage.getItem(key)!).round).toBe(2)
  expect(f.cloud.conflicts).toHaveLength(0)
  expect(f.cloud.status).toBe('云端进度已同步')
  expect(sameSave('{"version":1,"round":2}', '{"round":2,"version":1}')).toBe(true)
})
it('断网后继续本机保存，重试会识别已落库的请求，不重复提交', async () => {
  const f = fixture(); await f.cloud.refresh()
  localStorage.setItem(key, JSON.stringify({ version: 1, round: 3 }))
  f.put.mockImplementationOnce(async (_id, body) => { f.set({ ...body, game_id: id, revision: 1, updated_at: 1 }); throw new Error('断网') })
  await f.cloud.flush(id)
  expect(f.cloud.error).toContain('断网')
  await f.cloud.refresh(); await vi.advanceTimersByTimeAsync(2000)
  expect(f.put).toHaveBeenCalledTimes(1)
  expect(f.cloud.error).toBe('')
})
it('上传期间的新编辑不会被旧响应覆盖，页面销毁后迟到的读取不写入存档', async () => {
  const f = fixture(); await f.cloud.refresh()
  let done!: (value: Save) => void
  f.put.mockImplementationOnce(() => new Promise(resolve => { done = resolve }))
  localStorage.setItem(key, JSON.stringify({ version: 1, round: 1 }))
  const first = f.cloud.flush(id); await Promise.resolve()
  localStorage.setItem(key, JSON.stringify({ version: 1, round: 2 }))
  done(snapshot(1)); f.set(snapshot(1)); await first; await vi.advanceTimersByTimeAsync(2000)
  expect(f.put).toHaveBeenLastCalledWith(id, expect.objectContaining({ progress: { version: 1, round: 2 }, revision: 1 }))
  let finish!: (value: Save[]) => void
  const delayed = fixture(); delayed.list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const pending = delayed.cloud.refresh(); delayed.cloud.dispose(); finish([snapshot(8)]); await pending
  expect(JSON.parse(localStorage.getItem(key)!).round).toBe(2)
})
it('实际游戏校验拒绝损坏云存档，最近游戏显示真实关卡星数', async () => {
  expect(await validSave(id, JSON.stringify(newRocket()))).toBe(true)
  expect(await validSave(id, '{"version":1}')).toBe(false)
  const maze = newMaze(); maze.stars[0] = 3; maze.level = 1
  writeGameSave(gameKey('robot-maze'), maze)
  expect(localProgress('robot-maze', '')?.label).toBe('第 2 关 · 已获 3 星')
})

it('读取本机存档失败时显示可重试错误，不继续上传或抛出未处理异常', async () => {
  const f = fixture(); await f.cloud.refresh()
  vi.stubGlobal('localStorage', { getItem: () => { throw new Error('存储不可用') } })
  await expect(f.cloud.flush(id)).resolves.toBeUndefined()
  expect(f.cloud.error).toContain('存储不可用'); expect(f.put).not.toHaveBeenCalled()
})

it('损坏云存档与模块加载失败分别隔离，正常游戏仍恢复并上传，重试可恢复失败项', async () => {
  const other = 'little-shop' as const, third = 'word-spell' as const
  const records: Save[] = [snapshot(1), { ...snapshot(1), game_id: other }, { ...snapshot(1), game_id: third }]
  const list = vi.fn(async () => records)
  const put = vi.fn(async (game_id, body) => ({ ...body, game_id, revision: body.revision + 1, updated_at: 2 }))
  let recovered = false
  const validate = vi.fn(async game => {
    if (!recovered && game === other) return false
    if (!recovered && game === third) throw new Error('模块下载失败')
    return true
  })
  localStorage.setItem(gameKey(other, '7'), '原始本机内容')
  const cloud = new GameCloud('7', vi.fn(), { list, put }, validate); clouds.push(cloud)
  await cloud.refresh()
  expect(cloud.ready).toBe(true)
  expect(cloud.error).toContain('云端存档无法读取'); expect(cloud.error).toContain('模块下载失败')
  expect(localStorage.getItem(gameKey(other, '7'))).toBe('原始本机内容')
  expect(JSON.parse(localStorage.getItem(key)!)).toEqual(snapshot(1).progress)
  localStorage.setItem(key, JSON.stringify({ version: 1, round: 3 }))
  await cloud.flush(id)
  expect(put).toHaveBeenCalledOnce()
  expect(cloud.error).toContain('模块下载失败')
  await cloud.flush(other); expect(put).toHaveBeenCalledOnce()
  recovered = true; await cloud.refresh()
  expect(cloud.error).toBe('')
  expect(cloud.conflicts.map(item => item.id)).toContain(other)
  expect(localStorage.getItem(gameKey(third, '7'))).not.toBeNull()
})

it('一个游戏上传失败不阻止其他游戏保存，成功响应不清除其他游戏的错误', async () => {
  const other = 'little-shop' as const
  const put = vi.fn(async (game_id, body) => {
    if (game_id === other) throw new Error('小店连接中断')
    return { ...body, game_id, revision: body.revision + 1, updated_at: 1 }
  })
  const cloud = new GameCloud('7', vi.fn(), { list: async () => [], put }, async () => true); clouds.push(cloud)
  await cloud.refresh()
  localStorage.setItem(gameKey(other, '7'), '{"version":1}')
  localStorage.setItem(key, JSON.stringify(snapshot(1).progress))
  await cloud.flush(other); await cloud.flush(id)
  expect(put).toHaveBeenCalledTimes(2)
  expect(cloud.ready).toBe(true); expect(cloud.error).toContain('小店连接中断')
})

it('同时上传时出现冲突，等待其余上传结束后核对，避免丢失冲突刷新', async () => {
  const other = 'little-shop' as const
  let finish!: (value: Save) => void
  const list = vi.fn(async () => [snapshot(1)])
  const put = vi.fn((game_id) => game_id === other ? new Promise<Save>(resolve => { finish = resolve }) : Promise.reject(new ApiError('conflict', 409)))
  const cloud = new GameCloud('7', vi.fn(), { list, put }, async () => true); clouds.push(cloud)
  await cloud.refresh()
  localStorage.setItem(key, JSON.stringify(snapshot(3).progress))
  localStorage.setItem(gameKey(other, '7'), '{"version":1}')
  list.mockResolvedValue([snapshot(2)])
  const pending = cloud.flush(other); await Promise.resolve()
  await cloud.flush(id)
  expect(list).toHaveBeenCalledTimes(1)
  finish({ ...snapshot(1), game_id: other }); await pending
  expect(list).toHaveBeenCalledTimes(2); expect(cloud.conflicts.some(item => item.id === id)).toBe(true)
})
