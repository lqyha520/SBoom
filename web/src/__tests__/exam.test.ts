import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useExamStore } from '../stores/exam'
import * as api from '../api'
import { MAX_QUESTIONS_PER_TYPE } from '../constants'
import type { ScopeData } from '../types'

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  fetchAvailable: vi.fn().mockResolvedValue({}), fetchTemplates: vi.fn().mockResolvedValue([]),
  fetchScope: vi.fn().mockResolvedValue({ allowed: [] }),
  generateBatch: vi.fn(), upsertTemplate: vi.fn().mockResolvedValue(1),
  fetchGenerationUsage: vi.fn().mockResolvedValue(null),
  deleteTemplateOnServer: vi.fn().mockResolvedValue(undefined),
}))

function readyStore() {
  const store = useExamStore()
  store.ownerId = "1"; store.persistenceReady = true
  vi.spyOn(store, "flushDraft").mockResolvedValue(true)
  vi.spyOn(store, "saveHistory").mockResolvedValue(true)
  store.grade = '小学三年级'
  store.subject = '数学'
  store.keyword = '加减法'
  store.addSection('fill_blank', 4)
  return store
}
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); vi.useFakeTimers() })
afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers() })

describe('generation controls', () => {
  it('requires complete conditions and at least one section', async () => {
    const store = useExamStore()
  store.ownerId = "1"; store.persistenceReady = true
  vi.spyOn(store, "flushDraft").mockResolvedValue(true)
  vi.spyOn(store, "saveHistory").mockResolvedValue(true)
    expect(store.canGenerate).toBe(false)
    store.addSection('fill_blank')
    await store.generate()
    expect(api.generateBatch).not.toHaveBeenCalled()
    store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '  '
    expect(store.canGenerate).toBe(false)
    store.keyword = '加减法'
    expect(store.canGenerate).toBe(true)
    store.generating = true
    expect(store.canGenerate).toBe(false)
  })
  it('normalizes the count controls to the backend range', () => {
    const store = readyStore()
    const id = store.sections[0].id
    store.setSectionCount(id, 100)
    expect(store.sections[0].count).toBe(MAX_QUESTIONS_PER_TYPE)
    expect(store.sections[0].data!.questions).toHaveLength(MAX_QUESTIONS_PER_TYPE)
    store.setSectionCount(id, 0)
    expect(store.sections[0].count).toBe(1)
    store.setSectionCount(id, 4.7)
    expect(store.sections[0].count).toBe(5)
  })
  it('does not truncate an old template silently but blocks invalid generation', () => {
    const store = readyStore()
    store.sections[0].count = 99
    expect(store.canGenerate).toBe(false)
    expect(store.generationIssue).toContain('30')
    expect(store.sections[0].count).toBe(99)
  })
  it('blocks more than ten unique types while allowing repeated sections', () => {
    const store = readyStore()
    for (let i = 0; i < 15; i++) store.addSection('fill_blank')
    expect(store.canGenerate).toBe(true)
    for (let i = 0; i < 10; i++) store.addSection('type-' + i)
    expect(store.canGenerate).toBe(false)
    expect(store.generationIssue).toContain('10')
  })
  it('keeps section IDs and edited questions when sorting', () => {
    const store = readyStore()
    const first = store.sections[0]
    first.data!.questions[0].stem = 'Edited question'
    store.addSection('quiz')
    store.moveSection(0, 1)
    expect(store.sections[1].id).toBe(first.id)
    expect(store.sections[1].data!.questions[0].stem).toBe('Edited question')
    const ids = store.sections.map(s => s.id)
    store.moveSection(0, -1)
    expect(store.sections.map(s => s.id)).toEqual(ids)
  })
  it('creates selectable independent papers without sharing question objects', async () => {
    const store = readyStore()
    store.paperCount = 2
    vi.mocked(api.generateBatch).mockImplementation(async () => [{ game_type: 'fill_blank', questions: [{ type: 'fill_blank', stem: '1 + 1 =', answer: '2' }] }])
    await store.generate()
    expect(store.view).toBe('result')
    expect(store.papers).toHaveLength(2)
    expect(store.papers.map(p => p.day)).toEqual([1, 2])
    store.papers[0].sections[0].data.questions[0].stem = 'Edited first paper'
    expect(store.papers[1].sections[0].data.questions[0].stem).toBe('1 + 1 =')
    expect(store.generating).toBe(false)
  })
})

describe('condition switching', () => {
  it('clears old knowledge selections when switching subjects', async () => {
    const store = readyStore()
    store.selectedTags = ['old topic']
    await store.selectSubject('语文')
    expect(store.keyword).toBe('')
    expect(store.selectedTags).toEqual([])
  })
  it('ignores an outdated knowledge response after the grade changes', async () => {
    const store = readyStore()
    let resolve!: (value: ScopeData) => void
    vi.mocked(api.fetchScope).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const pending = store.selectSubject('数学')
    store.selectGrade('小学四年级')
    resolve({ allowed: ['old topic'] })
    await pending
    expect(store.scope).toBeNull()
    expect(store.scopeLoading).toBe(false)
  })
  it('does not change generation conditions mid-request', async () => {
    const store = readyStore()
    store.generating = true
    store.selectGrade('小学一年级')
    await store.selectSubject('语文')
    expect(store.grade).toBe('小学三年级')
    expect(store.subject).toBe('数学')
  })
})

describe('template round trips', () => {
  it('preserves rich text, section layout and independent snapshots', async () => {
    const store = readyStore()
    store.title = 'Daily practice'
    store.sections[0].data!.questions[0]._stemHtml = '<b>Edited</b>'
    store.sections[0].layout.qCols = 2
    expect(await store.saveMyTemplate('Saved')).toEqual({ local: true, synced: true })
    store.sections[0].data!.questions[0]._stemHtml = 'Different'
    expect(await store.loadMyTemplate('Saved')).toBe(true)
    expect(store.sections[0].data!.questions[0]._stemHtml).toBe('<b>Edited</b>')
    expect(store.sections[0].layout.qCols).toBe(2)
    expect(store.keyword).toBe('加减法')
    expect(api.upsertTemplate).toHaveBeenCalledOnce()
  })
  it('替换前保存历史，撤销完整恢复条件和生成结果', async () => {
    const store = readyStore()
    await store.saveMyTemplate('Saved')
    store.title = '原试卷'; store.grade = '小学六年级'; store.subject = '语文'; store.keyword = '古诗'; store.selectedTags = ['古诗']
    store.difficulty = 'hard'; store.view = 'result'
    store.papers = [{ grade: store.grade, subject: store.subject, keyword: store.keyword, difficulty: 'hard', title: '原试卷', sections: [] }]
    store.undoStack = []
    const original = store.editSnapshot()
    expect(await store.loadMyTemplate('Saved')).toBe(true)
    expect(store.saveHistory).toHaveBeenCalledWith('before-restore')
    expect(store.view).toBe('build'); expect(store.papers).toEqual([])
    store.undo()
    expect(store.editSnapshot()).toEqual(original)
  })
  it('恢复版本保存失败时不会覆盖当前试卷', async () => {
    const store = readyStore()
    await store.saveMyTemplate('Saved')
    store.title = '必须保留'
    vi.mocked(store.saveHistory).mockResolvedValue(false)
    expect(await store.loadMyTemplate('Saved')).toBe(false)
    expect(store.title).toBe('必须保留')
  })
  it('overwrites by name instead of duplicating templates', async () => {
    const store = readyStore()
    await store.saveMyTemplate('Saved')
    store.title = 'Updated'
    await store.saveMyTemplate('Saved')
    expect(store.myTemplates).toHaveLength(1)
    expect(store.myTemplates[0].title).toBe('Updated')
  })
  it('distinguishes local saving from failed server synchronization', async () => {
    const store = readyStore()
    vi.mocked(api.upsertTemplate).mockRejectedValueOnce(new Error('offline'))
    expect(await store.saveMyTemplate('Offline')).toEqual({ local: true, synced: false })
    expect(await store.loadMyTemplate('Offline')).toBe(true)
  })
  it('updates custom template configuration reactively', () => {
    const store = readyStore()
    store.saveCustomTemplate({ titlePrefix: 'Custom', showInfoRow: false })
    expect(store.templateId).toBe('custom')
    expect(store.template.titlePrefix).toBe('Custom')
    expect(store.template.showInfoRow).toBe(false)
  })
})
