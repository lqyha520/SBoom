import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as api from '../api'
import * as persistence from '../persistence'
import { useExamStore } from '../stores/exam'
import { UID_KEY, useAuthStore, userPrefix } from '../stores/auth'
import { LS } from '../constants'

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  fetchScope: vi.fn().mockResolvedValue({ allowed: [] }),
  fetchTemplates: vi.fn().mockResolvedValue([]),
  upsertTemplate: vi.fn().mockResolvedValue(1),
  deleteTemplateOnServer: vi.fn().mockResolvedValue(undefined),
}))

const stores: ReturnType<typeof useExamStore>[] = []
function account(id = 1) {
  setActivePinia(createPinia())
  useAuthStore().user = { id, username: 'teacher-' + id, role: 'user' }
  const store = useExamStore()
  stores.push(store)
  return store
}

beforeEach(async () => {
  localStorage.clear(); sessionStorage.clear()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('learn-coach-workspaces')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
  vi.mocked(api.fetchTemplates).mockResolvedValue([])
})
afterEach(async () => {
  for (const store of stores) { store.disposePersistence(); store.$dispose() }
  stores.length = 0
})

describe('owned drafts and immutable history', () => {
  it('binds storage to the authenticated user rather than the import-time localStorage ID', () => {
    localStorage.setItem(UID_KEY, '99')
    localStorage.setItem(userPrefix(1) + LS.paperStyle, JSON.stringify({ bg: 'stars' }))
    const store = account(1)
    expect(store.ownerId).toBe('1')
    expect(store.style.bg).toBe('stars')
  })

  it('restores a full draft on reload without exposing it to another account', async () => {
    const first = account(1)
    await first.initPersistence()
    first.grade = '小学三年级'; first.subject = '语文'; first.keyword = '阅读理解'; first.title = 'Reading'
    first.addSection('reading', 3)
    first.sections[0].data!.passage = 'Saved passage'
    first.sections[0].data!.questions[0]._stemHtml = '<b>Edited question</b>'
    first.style.bg = 'grid'
    expect(await first.flushDraft()).toBe(true)
    first.disposePersistence()
    const reload = account(1)
    await reload.initPersistence()
    expect(reload.title).toBe('Reading')
    expect(reload.sections[0].data!.passage).toBe('Saved passage')
    expect(reload.sections[0].data!.questions[0]._stemHtml).toBe('<b>Edited question</b>')
    expect(reload.style.bg).toBe('grid')
    const other = account(2)
    await other.initPersistence()
    expect(other.sections).toEqual([])
    expect(other.history).toEqual([])
  })

  it('uses independent writers even when a new tab inherits sessionStorage', async () => {
    const first = persistence.draftSession('1')
    const second = persistence.draftSession('1')
    expect(first.current).not.toBe(second.current)
    expect(second.previous).toBe(first.current)
    const store = account()
    const one = store.captureSnapshot(); one.title = 'One'
    const two = store.captureSnapshot(); two.title = 'Two'
    await persistence.saveDraft('1', first.current, one)
    await persistence.saveDraft('1', second.current, two)
    expect((await persistence.loadDraft('1', first.current))?.snapshot.title).toBe('One')
    expect((await persistence.loadDraft('1', second.current))?.snapshot.title).toBe('Two')
  })

  it('keeps history immutable and saves a recovery version before restoring', async () => {
    const store = account()
    await store.initPersistence()
    store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加法'; store.title = 'Version A'
    store.addSection('fill_blank', 4)
    expect(await store.saveVersion()).toBe(true)
    const id = store.history[0].id
    store.title = 'Version B'
    expect(await store.restoreHistory(id)).toBe(true)
    expect(store.title).toBe('Version A')
    const recovery = store.history.find(entry => entry.reason === 'before-restore')!
    expect((await persistence.getHistory('1', recovery.id)).title).toBe('Version B')
    store.title = 'Edited after restore'
    expect((await persistence.getHistory('1', id)).title).toBe('Version A')
    await expect(persistence.getHistory('2', id)).rejects.toThrow('不存在')
    await persistence.removeHistory('2', id)
    expect((await persistence.getHistory('1', id)).title).toBe('Version A')
  })

  it('does not replace current work when the recovery copy cannot be saved', async () => {
    const store = account()
    await store.initPersistence()
    store.addSection('fill_blank', 2)
    store.title = 'Old'; await store.saveVersion()
    const id = store.history[0].id
    store.title = 'Current'
    vi.spyOn(persistence, 'addHistory').mockRejectedValueOnce(new Error('Quota exceeded'))
    expect(await store.restoreHistory(id)).toBe(false)
    expect(store.title).toBe('Current')
    expect(store.storageError).toContain('保存失败')
  })

  it('surfaces quota failures without clearing the workspace', async () => {
    const store = account()
    await store.initPersistence()
    store.title = 'Unsaved data'
    vi.spyOn(persistence, 'saveDraft').mockRejectedValueOnce(new DOMException('Full', 'QuotaExceededError'))
    expect(await store.flushDraft()).toBe(false)
    expect(store.draftState).toBe('error')
    expect(store.title).toBe('Unsaved data')
  })

  it('flushes to the original owner and blocks generation after an account change', async () => {
    const store = account(1)
    await store.initPersistence()
    store.title = 'User one'
    useAuthStore().user = { id: 2, username: 'other', role: 'user' }
    expect(await store.suspendForAccountChange()).toBe(true)
    expect((await persistence.loadDraft('1'))?.snapshot.title).toBe('User one')
    expect(await persistence.loadDraft('2')).toBeNull()
    expect(store.canGenerate).toBe(false)
  })

  it('keeps an unsaved workspace suspended until saving to the original account succeeds', async () => {
    const store = account(1)
    await store.initPersistence()
    store.title = 'Unsaved original account'
    useAuthStore().user = { id: 2, username: 'other', role: 'user' }
    vi.spyOn(persistence, 'saveDraft').mockRejectedValueOnce(new DOMException('Full', 'QuotaExceededError'))
    expect(await store.suspendForAccountChange()).toBe(false)
    expect(store.title).toBe('Unsaved original account')
    expect(store.accountChanged).toBe(true)
    expect(store.draftState).toBe('error')
    expect(await store.suspendForAccountChange()).toBe(true)
    expect((await persistence.loadDraft('1'))?.snapshot.title).toBe('Unsaved original account')
    expect(await persistence.loadDraft('2')).toBeNull()
  })
})

describe('offline and conflicting templates', () => {
  it('retains local edits when a different remote revision arrives', async () => {
    const store = account()
    store.addSection('fill_blank', 2)
    store.title = 'Local edit'
    vi.mocked(api.upsertTemplate).mockRejectedValueOnce(new Error('offline'))
    expect(await store.saveMyTemplate('Lesson')).toEqual({ local: true, synced: false })
    const saved = JSON.parse(localStorage.getItem(userPrefix(1) + LS.myTemplates)!)[0]
    expect(saved._syncState).toBe('pending')
    vi.mocked(api.fetchTemplates).mockResolvedValueOnce([{ ...saved, title: 'Remote edit', _revision: 2, _syncState: 'synced' }])
    await store.syncTemplatesFromServer()
    expect(store.myTemplates[0].title).toBe('Local edit')
    expect(store.myTemplates[0]._syncState).toBe('conflict')
    expect(api.upsertTemplate).toHaveBeenCalledOnce()
  })

  it('does not remove the local template if server deletion fails', async () => {
    const store = account()
    store.addSection('fill_blank', 2)
    await store.saveMyTemplate('Lesson')
    vi.mocked(api.deleteTemplateOnServer).mockRejectedValueOnce(new Error('offline'))
    await expect(store.deleteMyTemplate('Lesson')).rejects.toThrow('offline')
    expect(store.myTemplates).toHaveLength(1)
    expect(JSON.parse(localStorage.getItem(userPrefix(1) + LS.myTemplates)!)).toHaveLength(1)
  })

  it('can preserve a conflicting version under a new name', async () => {
    const store = account()
    store.addSection('fill_blank', 2)
    await store.saveMyTemplate('Lesson')
    store.myTemplates[0]._syncState = 'conflict'
    expect(await store.copyMyTemplate('Lesson', 'Lesson copy')).toBe(true)
    expect(store.myTemplates).toHaveLength(2)
    const calls = vi.mocked(api.upsertTemplate).mock.calls
    const sent = calls[calls.length - 1]![0]
    expect(sent.name).toBe('Lesson copy')
    expect(sent._revision).toBe(0)
  })
})
