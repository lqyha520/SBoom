import 'fake-indexeddb/auto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { openDB } from 'idb'
import { useExamStore } from '../stores/exam'
import { addHistory, listHistory, loadDraft, saveDraft, pruneWorkspace, listDrafts } from '../persistence'
import { clearAccountData, storageUsage } from '../local-storage'

beforeEach(async () => {
  localStorage.clear(); sessionStorage.clear(); setActivePinia(createPinia())
  for (const name of ['learn-coach-workspaces', 'lc-worksheet-images']) await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error)
  })
})
afterEach(() => vi.restoreAllMocks())

it('保留最近草稿并跳过当前页、其他活跃标签页和其他账号', async () => {
  const snapshot = useExamStore().captureSnapshot()
  const time = vi.spyOn(Date, 'now')
  for (let index = 0; index < 14; index++) { time.mockReturnValue(1000 + index); await saveDraft('1', String(index), snapshot) }
  await saveDraft('2', 'other', snapshot)
  time.mockReturnValue(3 * 86400000)
  vi.stubGlobal('navigator', { locks: { request: vi.fn(async (name, _options, run) => run(name === 'lc-draft:1:1' ? null : {})) } })
  try {
    await pruneWorkspace('1', '0')
    const ids = (await listDrafts('1')).map(value => value.id)
    expect(ids).toHaveLength(12)
    expect(ids).toContain('1:0'); expect(ids).toContain('1:1')
    expect(ids).not.toContain('1:2'); expect(ids).not.toContain('1:3')
    expect(await listDrafts('2')).toHaveLength(1)
  } finally { vi.unstubAllGlobals() }
})

it('历史版本限制为每账号 100 份，并保留其他账号', async () => {
  const snapshot = useExamStore().captureSnapshot()
  await addHistory('2', snapshot, 'manual')
  for (let index = 0; index < 104; index++) await addHistory('1', { ...snapshot, title: String(index) }, 'generated')
  expect(await listHistory('1', { limit: 100 })).toHaveLength(100)
  expect(await listHistory('2')).toHaveLength(1)
})

it('退出清理只删除本账号数据，并阻止旧页面把草稿重新写回', async () => {
  const snapshot = useExamStore().captureSnapshot()
  for (const owner of ['1', '2']) { await saveDraft(owner, 'test', snapshot); await addHistory(owner, snapshot, 'manual'); localStorage.setItem(`lc_u${owner}_image_request`, 'private') }
  const db = await openDB('lc-worksheet-images', 1, { upgrade(value) { value.createObjectStore('images') } })
  await db.put('images', 'private image 1', 'lc_u1_image_request:x')
  await db.put('images', 'private image 2', 'lc_u2_image_request:x')
  await clearAccountData('1')
  expect(await loadDraft('1')).toBeNull(); expect(await listHistory('1')).toEqual([])
  expect(await loadDraft('2')).not.toBeNull(); expect(await listHistory('2')).toHaveLength(1)
  expect(await db.get('images', 'lc_u1_image_request:x')).toBeUndefined()
  expect(await db.get('images', 'lc_u2_image_request:x')).toBe('private image 2')
  expect(localStorage.getItem('lc_u1_image_request')).toBeNull()
  expect(localStorage.getItem('lc_u2_image_request')).toBe('private')
  await expect(saveDraft('1', 'late', snapshot)).rejects.toThrow('本机数据已清除')
  db.close()
})

it('持久化申请被浏览器拒绝仍报告用量', async () => {
  vi.stubGlobal('navigator', { storage: { estimate: async () => ({ usage: 1024, quota: 4096 }), persisted: async () => false, persist: async () => false } })
  try { expect(await storageUsage(true)).toEqual({ usage: 1024, quota: 4096, persisted: false }) }
  finally { vi.unstubAllGlobals() }
})
