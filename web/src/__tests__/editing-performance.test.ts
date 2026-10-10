import { beforeEach, expect, it } from 'vitest'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useExamStore } from '../stores/exam'
import { captureEdit } from '../workspace-history'
import { createSectionSignatures, createSectionMeasurements } from '../section-measurement'
import { DEFAULT_LAYOUT } from '../constants'
import type { PaperSection } from '../types'

beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })

it('连续编辑共享未变化试卷，旧撤销快照不会随新题变化', () => {
  const store = useExamStore()
  store.ownerId = '7'; store.persistenceReady = true
  store.papers = Array.from({ length: 20 }, (_, index) => ({
    title: `试卷${index}`, grade: '三年级', subject: '数学', keyword: '加法', difficulty: 'medium',
    sections: [{ type: 'quiz', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '1+1', answer: '2' }, { stem: '2+2', answer: '4' }] } }],
  }))
  const first = captureEdit(store)
  store.recordEdit()
  store.papers[0].sections[0].data.questions[0].stem = '1+2'
  const second = captureEdit(store)
  expect(second.papers[19]).toBe(first.papers[19])
  expect(second.papers[0].sections[0].data.questions[1]).toBe(first.papers[0].sections[0].data.questions[1])
  expect(first.papers[0].sections[0].data.questions[0].stem).toBe('1+1')
  store.undo()
  expect(store.papers[0].sections[0].data.questions[0].stem).toBe('1+1')
  store.redo()
  expect(store.papers[0].sections[0].data.questions[0].stem).toBe('1+2')
  store.recordEdit()
  store.papers[0].sections[0].data.questions.push({ stem: '3+3', answer: '6' })
  store.undo()
  expect(store.papers[0].sections[0].data.questions).toHaveLength(2)
})

it('标题编辑共享所有题目，删除和重新排序后仍可正确撤销', () => {
  const store = useExamStore()
  store.ownerId = '7'; store.persistenceReady = true
  store.addSection('quiz', 2); store.addSection('oral_math', 3)
  const first = captureEdit(store)
  store.setTitle('新的标题')
  expect(captureEdit(store).sections).toBe(first.sections)
  store.undo()
  expect(store.title).toBe(first.title)
  const original = store.sections.map(section => section.id)
  store.recordEdit()
  store.sections.reverse()
  store.undo()
  expect(store.sections.map(section => section.id)).toEqual(original)
  store.redo()
  expect(store.sections.map(section => section.id)).toEqual([...original].reverse())
})

it('仅重测变化的大题，字号、字体及排序变化会重新核验几何信息', () => {
  const sections = reactive<PaperSection[]>(Array.from({ length: 3 }, (_, index) => ({
    _sid: `s${index}`, type: 'quiz', layout: { ...DEFAULT_LAYOUT },
    data: { questions: [{ stem: `题目${index}`, answer: '1', _locked: false }] },
  })))
  const signature = createSectionSignatures(), cache = createSectionMeasurements()
  let keys = sections.map(signature)
  expect(cache.dirty(keys, 'normal')).toEqual([0, 1, 2])
  const measured = new Map(sections.map((_, sec) => [sec, { sec, total: 1, headBlockH: 30, rows: [40], rowStride: 1 }]))
  cache.commit(keys, 'normal', measured)
  sections[0].data.questions[0]._locked = true
  expect(cache.dirty(sections.map(signature), 'normal')).toEqual([])
  sections[1].data.questions[0].stem = '更长的题目'
  keys = sections.map(signature)
  expect(cache.dirty(keys, 'normal')).toEqual([1])
  const result = cache.commit(keys, 'normal', new Map([[1, { ...measured.get(1)!, rows: [80] }]]))
  expect(result[0]).toBe(measured.get(0))
  expect(result[1].rows).toEqual([80])
  expect(cache.dirty(keys, 'large-font')).toEqual([0, 1, 2])
  sections.reverse()
  expect(cache.dirty(sections.map(signature), 'normal')).toEqual([0, 2])
})
