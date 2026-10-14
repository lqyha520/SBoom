import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useExamStore } from '../stores/exam'
import * as api from '../api'
import { createGenerationRun, assemblePaper } from '../generation'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(),
  generateBatch: vi.fn(), fetchGenerationStatus: vi.fn(), fetchGenerationUsage: vi.fn().mockResolvedValue(null) }))
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); vi.clearAllMocks() })
afterEach(() => vi.unstubAllGlobals())
function ready(count = 3) {
  const store = useExamStore()
  store.ownerId = "1"; store.persistenceReady = true
  vi.spyOn(store, "flushDraft").mockResolvedValue(true)
  vi.spyOn(store, "saveHistory").mockResolvedValue(true)
  store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加减法'
  store.addSection('fill_blank', count)
  store.sections[0].data = { questions: Array.from({ length: count }, (_, index) => ({
    type: 'fill_blank', stem: `已有题目 ${index + 1}`, answer: '2',
  })) }
  store.questionSection(store.sections[0].id)
  return store
}
function response(items: api.BatchItemReq[]) {
  return items.map(item => ({ game_type: item.game_type, section_id: item.section_id,
    questions: Array.from({ length: item.question_count }, (_, index) => ({ stem: `新题 ${index}：8+9=__`, answer: '17' })) }))
}

describe('编辑恢复与单题替换', () => {
  it('排版取消恢复样式、题目和历史，完成可一步撤销', () => {
    const store = ready()
    const original = store.editSnapshot()
    const undo = [...store.undoStack]
    store.beginLayout()
    store.setStyle({ titleOffsetY: 9 })
    store.sections[0].layout.qCols = 1
    store.sections[0].data!.questions.pop()
    store.finishLayout(true)
    expect(store.editSnapshot()).toEqual(original)
    expect(store.undoStack).toEqual(undo)
    store.beginLayout()
    store.setStyle({ titleOffsetY: 3 })
    store.finishLayout()
    store.undo()
    expect(store.style.titleOffsetY).toBe(original.style.titleOffsetY)
    store.redo()
    expect(store.style.titleOffsetY).toBe(3)
  })
  it('已有结果的所有新生成入口都先确认，取消不产生调用', async () => {
    const store = ready()
    const generate = vi.spyOn(store, 'generate').mockResolvedValue()
    await store.requestGeneration()
    expect(generate).toHaveBeenCalledOnce()
    store.pendingRun = createGenerationRun({ grade: store.grade, subject: store.subject, keyword: store.keyword, title: '', difficulty: store.difficulty, hiddenElements: [], count: 1, sections: [] })
    const confirm = vi.fn(() => false)
    vi.stubGlobal('confirm', confirm)
    await store.requestGeneration()
    expect(confirm).toHaveBeenCalledOnce()
    expect(generate).toHaveBeenCalledOnce()
    confirm.mockReturnValue(true)
    await store.requestGeneration()
    expect(generate).toHaveBeenCalledTimes(2)
  })
  it('连续标题输入合并为一步撤销，排版期间暂停撤销', () => {
    const store = ready()
    store.undoStack = []
    store.setTitle('三'); store.setTitle('三年'); store.setTitle('三年级')
    expect(store.undoStack).toHaveLength(1)
    store.layoutMode = true; store.undo(); expect(store.title).toBe('三年级')
    store.layoutMode = false; store.undo(); expect(store.title).toBe('')
    store.redo(); expect(store.title).toBe('三年级')
  })
  it('删除和减少题数都可撤销重做，新的编辑清除重做分支', () => {
    const store = ready(), id = store.sections[0].id
    store.sections[0].data!.questions[2]._stemHtml = '<b>人工编辑</b>'
    store.setSectionCount(id, 1)
    store.undo()
    expect(store.sections[0].data!.questions[2]._stemHtml).toBe('<b>人工编辑</b>')
    store.redo(); expect(store.sections[0].count).toBe(1)
    store.removeSection(id); store.undo(); expect(store.sections).toHaveLength(1)
    store.setSectionCount(id, 2); expect(store.canRedo).toBe(false)
  })
  it('换题只替换指定题目，稳定标识和其他题目保持，支持撤销', async () => {
    const store = ready(), section = store.sections[0], before = JSON.parse(JSON.stringify(section.data!.questions))
    vi.mocked(api.generateBatch).mockImplementation(async params => response(params.items))
    await store.replaceQuestion(section.id, before[1]._qid)
    expect(section.data!.questions[0]).toEqual(before[0])
    expect(section.data!.questions[2]).toEqual(before[2])
    expect(section.data!.questions[1]._qid).toBe(before[1]._qid)
    expect(section.data!.questions[1].stem).toContain('新题')
    store.undo(); expect(store.sections[0].data!.questions).toEqual(before)
  })
  it('锁定题不可替换或因减少题数移除', async () => {
    const store = ready(), section = store.sections[0], qid = section.data!.questions[2]._qid!
    store.toggleQuestionLock(section.id, qid)
    store.setSectionCount(section.id, 1)
    expect(section.count).toBe(3)
    await store.replaceQuestion(section.id, qid)
    expect(api.generateBatch).not.toHaveBeenCalled()
  })
  it('模型换题与已有题重复时保留原题，并允许重新换题', async () => {
    const store = ready(), section = store.sections[0]
    const first = section.data!.questions[0], repeated = section.data!.questions[1]
    const qid = first._qid!
    const original = JSON.parse(JSON.stringify(section.data!.questions))
    vi.mocked(api.generateBatch).mockResolvedValue([{ game_type: section.type, section_id: section.id,
      questions: [{ type: repeated.type, stem: repeated.stem, answer: repeated.answer }] }])
    await expect(store.replaceQuestion(section.id, qid)).rejects.toThrow('重复')
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(section.data!.questions).toHaveLength(3)
    expect(section.data!.questions).toEqual(original)
    expect(section.data!.questions[0]._qid).toBe(qid)
    expect(section.data!.questions[0]._replacement).toBeUndefined()
    expect(store.generating).toBe(false)
    vi.mocked(api.generateBatch).mockImplementation(async params => response(params.items))
    await store.replaceQuestion(section.id, qid)
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(section.data!.questions[0].stem).toContain('新题')
  })
  it('换题检查同卷其他大题，并识别全角和乘号的等价写法', async () => {
    const store = ready(), section = store.sections[0], original = section.data!.questions[0].stem
    store.addSection('fill_blank', 1)
    const other = store.sections[1]
    other.data = { questions: [{ type: 'fill_blank', stem: '9 × 2 = ___', answer: 18 }] }
    vi.mocked(api.generateBatch).mockResolvedValue([{ game_type: section.type, section_id: section.id,
      questions: [{ type: 'fill_blank', stem: '９*２＝___', answer: 18 }] }])
    await expect(store.replaceQuestion(section.id, section.data!.questions[0]._qid!)).rejects.toThrow('重复')
    expect(section.data!.questions[0].stem).toBe(original)
  })
  it('换题失败保留原题和请求记录，仍在处理时不重复发送', async () => {
    const store = ready(), section = store.sections[0], question = section.data!.questions[0], stem = question.stem
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new Error('网络超时'))
    await expect(store.replaceQuestion(section.id, question._qid!)).rejects.toThrow('网络超时')
    expect(question.stem).toBe(stem)
    expect(question._replacement).toBeTruthy()
    expect(store.canUndo).toBe(false)
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({ status: 'running' } as api.GenerationStatus)
    await expect(store.replaceQuestion(section.id, question._qid!)).rejects.toThrow('仍在处理中')
    expect(api.generateBatch).toHaveBeenCalledTimes(1)
  })
})

describe('锁定和停止生成', () => {
  it('不同结果卷各自保留锁题，未锁题的结果卷不继承搭建区锁题', async () => {
    const store = ready(2); store.paperCount = 3
    vi.mocked(api.generateBatch).mockImplementation(async params => response(params.items))
    await store.generate()
    const first = store.papers[0].sections[0].data.questions[0]
    const second = store.papers[1].sections[0].data.questions[1]
    first._locked = true; first.stem = '第一份保留'
    second._locked = true; second.stem = '第二份保留'
    store.sections[0].data!.questions[0]._locked = true
    vi.mocked(api.generateBatch).mockClear()
    await store.generate()
    expect(vi.mocked(api.generateBatch).mock.calls.map(([params]) => params.items[0].question_count)).toEqual([1, 1, 2])
    expect(store.papers[0].sections[0].data.questions[0].stem).toBe('第一份保留')
    expect(store.papers[1].sections[0].data.questions[1].stem).toBe('第二份保留')
    expect(store.papers[2].sections[0].data.questions.some(question => question._locked)).toBe(false)
  })
  it('重新生成仅请求未锁定题，原位置保留锁定题及富文本', async () => {
    const store = ready(), section = store.sections[0], locked = section.data!.questions[1]
    locked._locked = true; locked._stemHtml = '<b>保留题目</b>'
    vi.mocked(api.generateBatch).mockImplementation(async params => response(params.items))
    await store.generate()
    expect(vi.mocked(api.generateBatch).mock.calls[0][0].items[0].question_count).toBe(2)
    expect(store.papers[0].sections[0].data.questions[1]).toEqual(locked)
  })
  it('全部锁定不能把未调用模型的操作装配为新试卷', async () => {
    const store = ready(1), section = store.sections[0], question = section.data!.questions[0]
    question._locked = true
    const context = { grade: store.grade, subject: store.subject, keyword: store.keyword, title: '', difficulty: store.difficulty,
      hiddenElements: [], count: 1, sections: [{ ...section, lockedQuestions: [{ index: 0, question }] }] }
    const run = createGenerationRun(context)
    expect(run.jobs[0].chunks).toEqual([])
    expect(() => assemblePaper(context, run.jobs[0])).toThrow('没有待生成的题目')
    const before = store.editSnapshot()
    await store.generate()
    expect(api.generateBatch).not.toHaveBeenCalled()
    expect(store.generateError).toContain('没有待生成的题目')
    expect(store.editSnapshot()).toEqual(before)
    expect(store.pendingRun).toBeNull()
    await store.retrySection(section.id)
    expect(section.error).toContain('没有待生成的题目')
    expect(section.data!.questions).toEqual([question])
    expect(section.pendingGeneration).toBeUndefined()
  })
  it('任一结果卷全部锁定时不覆盖原结果和未完成请求', async () => {
    const store = ready(1); store.paperCount = 2
    vi.mocked(api.generateBatch).mockImplementation(async params => response(params.items))
    await store.generate()
    store.papers[1].sections[0].data.questions[0]._locked = true
    const before = store.editSnapshot()
    const pending = createGenerationRun({ grade: store.grade, subject: store.subject, keyword: store.keyword,
      title: '', difficulty: store.difficulty, hiddenElements: [], count: 1, sections: [] })
    store.pendingRun = pending
    vi.mocked(api.generateBatch).mockClear()
    await store.generate()
    expect(store.generateError).toContain('没有待生成的题目')
    expect(store.editSnapshot()).toEqual(before)
    expect(store.pendingRun).toEqual(pending)
    expect(api.generateBatch).not.toHaveBeenCalled()
  })
  it('停止后不派发排队任务，已经发出的一份继续完成', async () => {
    const store = ready(1); store.paperCount = 5
    const releases: (() => void)[] = []
    vi.mocked(api.generateBatch).mockImplementation(params => new Promise(resolve => { releases.push(() => resolve(response(params.items))) }))
    const running = store.generate()
    await vi.waitFor(() => expect(releases).toHaveLength(1))
    store.stopRequested = true
    releases.forEach(release => release())
    await running
    expect(api.generateBatch).toHaveBeenCalledTimes(1)
    expect(store.papers).toHaveLength(1)
    expect(store.pendingRun?.jobs).toHaveLength(4)
    expect(store.pendingRun?.jobs.every(job => job.chunks.every(chunk => chunk.state === 'new'))).toBe(true)
    expect(store.generationJobs.filter(job => job.finishedAt)).toHaveLength(1)
  })
})
