import 'fake-indexeddb/auto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useExamStore } from '../stores/exam'
import * as persistence from '../persistence'

beforeEach(async () => {
  sessionStorage.clear(); setActivePinia(createPinia())
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('learn-coach-workspaces')
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error)
  })
})
afterEach(() => vi.unstubAllGlobals())
const snapshot = () => useExamStore().captureSnapshot()

it('升级旧数据库时保留快照，后续历史查询只读取摘要', async () => {
  const value = snapshot()
  const entry = { id: 'legacy', owner: '1', updatedAt: 10, title: '旧版本', grade: '', subject: '', keyword: '', paperCount: 0, questionCount: 0, reason: 'manual' }
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.open('learn-coach-workspaces', 1)
    request.onupgradeneeded = () => {
      for (const name of ['drafts', 'history']) request.result.createObjectStore(name, { keyPath: 'id' }).createIndex('ownerUpdated', ['owner', 'updatedAt'])
      request.transaction!.objectStore('history').add({ ...entry, snapshot: value })
      request.transaction!.objectStore('drafts').add({ id: '1:old', owner: '1', updatedAt: 10, snapshot: value })
    }
    request.onsuccess = () => { request.result.close(); resolve() }; request.onerror = () => reject(request.error)
  })
  expect(await persistence.listHistory('1')).toEqual([entry])
  expect(await persistence.getHistory('1', 'legacy')).toEqual(value)
  expect((await persistence.loadDraft('1', 'old'))?.snapshot).toEqual(value)
  expect(await persistence.listDrafts('1')).toHaveLength(1)
  const transactions = vi.spyOn(IDBDatabase.prototype, 'transaction')
  await persistence.listHistory('1')
  expect(transactions.mock.calls.map(call => call[0])).toEqual(['historyMeta'])
})

it('历史分页没有重复或遗漏，搜索覆盖未加载页面，不读取题目快照', async () => {
  const value = snapshot(); value.titleHtml = '长试卷'.repeat(5000)
  for (let i = 0; i < 45; i++) await persistence.addHistory('1', { ...value, title: i === 3 ? '查找目标' : '版本' + i }, 'manual')
  const transactions = vi.spyOn(IDBDatabase.prototype, 'transaction')
  const first = await persistence.listHistory('1'), second = await persistence.listHistory('1', { offset: 20 }), third = await persistence.listHistory('1', { offset: 40 })
  expect([first.length, second.length, third.length]).toEqual([20, 20, 5])
  expect(new Set([...first, ...second, ...third].map(entry => entry.id)).size).toBe(45)
  expect((await persistence.listHistory('1', { query: '查找目标' })).map(entry => entry.title)).toEqual(['查找目标'])
  expect(transactions.mock.calls.every(call => call[0] === 'historyMeta')).toBe(true)
  await persistence.removeHistory('1', first[0].id)
  await expect(persistence.getHistory('1', first[0].id)).rejects.toThrow('不存在')
  expect(await persistence.listHistory('2')).toEqual([])
})

function locks() {
  const held = new Set<string>()
  vi.stubGlobal('navigator', { locks: { request: async (name: string, _options: unknown, callback: (lock: object | null) => unknown) => {
    if (held.has(name)) return callback(null)
    held.add(name)
    try { return await callback({ name }) } finally { held.delete(name) }
  } } })
}

it('刷新复用已释放的草稿，复制页面分配独立身份，活动草稿不能删除', async () => {
  locks()
  const first = await persistence.claimDraftSession('1', persistence.draftSession('1'))
  const second = await persistence.claimDraftSession('1', persistence.draftSession('1'))
  try {
    expect(first.current).not.toBe(second.current)
    await persistence.saveDraft('1', first.current, snapshot())
    const entry = (await persistence.listDrafts('1'))[0]
    await expect(persistence.removeDraft('1', entry, second.current)).rejects.toThrow('其他页面使用')
    first.release?.(); await Promise.resolve(); await Promise.resolve()
    const reload = await persistence.claimDraftSession('1', { previous: first.current, current: 'new-page' })
    try {
      expect(reload.current).toBe(first.current)
      await persistence.saveDraft('1', reload.current, snapshot())
      expect(await persistence.listDrafts('1')).toHaveLength(1)
    } finally { reload.release?.() }
  } finally { first.release?.(); second.release?.() }
})

it('手动清理核验账号、当前页面和修改时间，并同步删除摘要', async () => {
  vi.stubGlobal('navigator', {})
  vi.spyOn(Date, 'now').mockReturnValue(10)
  await persistence.saveDraft('1', 'old', snapshot())
  const entry = (await persistence.listDrafts('1'))[0]
  await expect(persistence.removeDraft('2', entry, 'current')).rejects.toThrow('其他账号')
  await expect(persistence.removeDraft('1', entry, 'old')).rejects.toThrow('当前页面')
  vi.mocked(Date.now).mockReturnValue(20)
  await persistence.saveDraft('1', 'old', snapshot())
  await expect(persistence.removeDraft('1', entry, 'current')).rejects.toThrow('已更新')
  await persistence.removeDraft('1', (await persistence.listDrafts('1'))[0], 'current')
  expect(await persistence.listDrafts('1')).toEqual([])
  expect(await persistence.loadDraft('1', 'old')).toBeNull()
})
