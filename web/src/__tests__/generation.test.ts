import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as api from '../api'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  generateBatch: vi.fn(),
  fetchGenerationUsage: vi.fn().mockResolvedValue(null),
  fetchGenerationStatus: vi.fn(),
}))

function ready() {
  const store = useExamStore()
  store.ownerId = "1"; store.persistenceReady = true
  vi.spyOn(store, "flushDraft").mockResolvedValue(true)
  vi.spyOn(store, "saveHistory").mockResolvedValue(true)
  store.grade = '小学三年级'
  store.subject = '数学'
  store.keyword = '加法'
  store.title = 'Original title'
  store.addSection('fill_blank', 4)
  return store
}

function result(params: api.BatchParams): api.BatchRespSection[] {
  return params.items.map(item => ({ game_type: item.game_type, section_id: item.section_id,
    passage: item.game_type === 'reading' ? 'Original passage' : undefined,
    questions: Array.from({ length: item.question_count }, (_, index) => ({ stem: item.section_id + ':' + index, answer: index })),
  }))
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.mocked(api.generateBatch).mockReset().mockImplementation(async params => result(params))
  vi.mocked(api.fetchGenerationStatus).mockReset().mockResolvedValue({ request_id: 'old', status: 'unknown', result: null, error_status: 504, cache_expired: false })
})
afterEach(() => useExamStore().disposePersistence())

describe('section-safe generation', () => {
  it('保留36题试卷中的28道有效题，缺失口算不算完成，手动只补8道', async () => {
    const store = ready()
    store.sections = []
    for (const [type, count] of [['oral_math', 8], ['fill_blank', 8], ['number_split', 8], ['compare', 6], ['true_false', 6]] as const)
      store.addSection(type, count)
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => {
      const partial = result(params)
      partial[0].questions = []
      partial[0].missing_count = 8
      throw new api.ApiError('缺少8道题', 422, 'generation_incomplete', '', partial)
    })
    await store.generate()
    const firstCalls = vi.mocked(api.generateBatch).mock.calls
    expect(firstCalls).toHaveLength(2)
    expect(firstCalls[1][0].previous_request_ids).toEqual([firstCalls[0][1]])
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([0, 8, 8, 6, 6])
    expect(store.failedCount).toBe(1)
    expect(store.pendingRun?.jobs).toHaveLength(1)
    store.papers[0].sections[1].data.questions[0].stem = '用户修改的题目'
    store.papers[0].title = '用户修改的标题'
    const kept = JSON.stringify(store.papers[0].sections.slice(1).map(section => section.data.questions))
    await store.recoverPending()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(store.failedCount).toBe(1)
    await store.retryFailed()
    const calls = vi.mocked(api.generateBatch).mock.calls
    expect(calls).toHaveLength(3)
    expect(calls[2][0].items).toEqual([{ section_id: store.sections[0].id, game_type: 'oral_math', question_count: 8 }])
    expect(calls[2][0].previous_request_ids).toEqual([calls[0][1], calls[1][1]])
    expect(store.papers).toHaveLength(1)
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([8, 8, 8, 6, 6])
    expect(JSON.stringify(store.papers[0].sections.slice(1).map(section => section.data.questions))).toBe(kept)
    expect(store.failedCount).toBe(0)
    expect(store.pendingRun).toBeNull()
    expect(store.papers[0].title).toBe('用户修改的标题')
  })

  it('兼容旧版成功但缺题响应，重复补齐仍不足时停止，不循环请求', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockImplementation(async params => result(params).map(section =>
      ({ ...section, questions: section.questions.slice(0, 1), missing_count: params.items[0].question_count - 1 })))
    await store.generate()
    expect(store.failedCount).toBe(1)
    await store.retryFailed()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.generateBatch).mock.calls[1][0].items[0].question_count).toBe(3)
    expect(store.papers).toHaveLength(1)
    expect(store.papers[0].sections[0].data.questions).toHaveLength(2)
    expect(store.pendingRun).not.toBeNull()
    expect(store.failedCount).toBe(1)
    expect(store.papers[0].sections[0].data.missing_count).toBe(2)
  })

  it('单大题未出齐时保留原任务，手动补齐只请求剩余题数', async () => {
    const store = ready(), section = store.sections[0]
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => {
      const partial = result(params).map(value => ({ ...value, questions: value.questions.slice(0, 2), missing_count: 2 }))
      throw new api.ApiError('缺题', 422, 'generation_incomplete', '', partial)
    })
    await store.retrySection(section.id)
    expect(section.status).toBe('error')
    expect(section.data?.questions).toHaveLength(2)
    expect(section.pendingGeneration).toBeDefined()
    const original = section.data!.questions.map(question => question.stem)
    await store.retrySection(section.id)
    expect(vi.mocked(api.generateBatch).mock.calls[1][0].items[0].question_count).toBe(2)
    expect(section.data?.questions.slice(0, 2).map(question => question.stem)).toEqual(original)
    expect(section.status).toBe('ready')
    expect(section.pendingGeneration).toBeUndefined()
  })

  it('查询到缺题终态后保留有效题，不自动付费补齐', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Network', 0))
    await store.generate()
    const [params, requestId] = vi.mocked(api.generateBatch).mock.calls[0]
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({
      request_id: requestId!, status: 'failed', result: null, error_status: 422, cache_expired: false,
      error: { code: 'generation_incomplete', partial_sections: result(params).map(value =>
        ({ ...value, questions: value.questions.slice(0, 2), missing_count: 2 })) },
    })
    await store.recoverPending()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.papers[0].sections[0].data.questions).toHaveLength(2)
    expect(store.failedCount).toBe(1)
    await store.retryFailed()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(store.failedCount).toBe(0)
  })

  it('阅读题缺题后手动重生成整篇，不混合新旧文章', async () => {
    const store = ready()
    store.sections = []
    store.addSection('reading', 4)
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => result(params).map(value =>
      ({ ...value, passage: '旧文章', questions: value.questions.slice(0, 2), missing_count: 2 })))
    await store.generate()
    expect(store.papers[0].sections[0].data.passage).toBe('旧文章')
    await store.retryFailed()
    expect(vi.mocked(api.generateBatch).mock.calls[1][0].items[0].question_count).toBe(4)
    expect(store.papers[0].sections[0].data.passage).toBe('Original passage')
    expect(store.papers).toHaveLength(1)
    expect(store.failedCount).toBe(0)
  })

  it.each(Object.keys(TYPE_NAME))('新增 %s 只设置题量，实际生成必须请求模型', async type => {
    const store = ready()
    store.sections = []
    store.addSection(type, 2)
    const section = store.sections[0]
    expect(section.data?.questions).toEqual([])
    store.setSectionCount(section.id, 3)
    expect(section.data?.questions).toEqual([])
    expect(store.totalQuestions).toBe(3)
    expect(api.generateBatch).not.toHaveBeenCalled()
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.papers[0].sections[0].data.questions).toHaveLength(3)
  })

  it('已生成大题增加题数时保留旧题，新增部分不以模拟题填充', async () => {
    const store = ready()
    await store.generate()
    const section = store.sections[0], questions = JSON.parse(JSON.stringify(section.data!.questions))
    store.setSectionCount(section.id, 6)
    expect(section.data!.questions).toEqual(questions)
    expect(section.data!.missing_count).toBe(2)
    expect(store.totalQuestions).toBe(6)
    expect(api.generateBatch).toHaveBeenCalledOnce()
    await store.retrySection(section.id)
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(section.data!.questions).toHaveLength(6)
  })

  it('相同条件重新生成和单独生成大题都会发送新请求，不复用旧结果', async () => {
    const store = ready()
    await store.generate()
    await store.regenerate()
    await store.retrySection(store.sections[0].id)
    await store.retrySection(store.sections[0].id)
    const ids = vi.mocked(api.generateBatch).mock.calls.map(([, id]) => id)
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(4)
    expect(api.fetchGenerationStatus).not.toHaveBeenCalled()
  })

  it('生成失败时新增大题保持空白，不显示模拟题', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('模型不可用', 502))
    await store.generate()
    expect(store.sections[0].data?.questions).toEqual([])
    expect(store.papers).toEqual([])
    expect(store.generateError).toBe('模型不可用')
  })

  it('历史草稿的输入不被静默改写为新版目录标签', async () => {
    const store = ready()
    const legacy = '上册·20以内的进位加法（凑十法：9加几、8加几）'
    store.grade = '小学一年级'
    store.keyword = legacy
    store.selectedTags = [legacy]
    await store.generate()
    expect(vi.mocked(api.generateBatch).mock.calls[0][0].keyword).toBe(legacy)
    expect(store.selectedTags).toEqual([legacy])
  })

  it('后续分块引用本卷已完成请求，下一份试卷重新开始上下文', async () => {
    const store = ready()
    store.sections[0].count = 30
    store.addSection('true_false', 6)
    store.paperCount = 2
    await store.generate()
    const calls = vi.mocked(api.generateBatch).mock.calls
    expect(calls).toHaveLength(4)
    expect(calls[0][0].previous_request_ids).toBeUndefined()
    expect(calls[1][0].previous_request_ids).toEqual([calls[0][1]])
    expect(calls[2][0].previous_request_ids).toBeUndefined()
    expect(calls[3][0].previous_request_ids).toEqual([calls[2][1]])
  })

  it('生成中留在搭建页，整批完成后再显示结果', async () => {
    const store = ready()
    store.paperCount = 2
    // 从旧结果页重新生成也应先显示搭建页的进度。
    store.view = 'result'
    const releases: (() => void)[] = []
    vi.mocked(api.generateBatch).mockImplementation(params => new Promise(resolve => {
      releases.push(() => resolve(result(params)))
    }))
    const pending = store.generate()
    await vi.waitFor(() => expect(releases).toHaveLength(1))
    expect(api.generateBatch).toHaveBeenCalledTimes(1)
    expect(store.view).toBe('build')
    expect(store.generating).toBe(true)
    expect(store.papers).toHaveLength(0)
    releases[0]()
    await vi.waitFor(() => expect(releases).toHaveLength(2))
    expect(store.papers).toHaveLength(1)
    expect(store.view).toBe('build')
    expect(store.generating).toBe(true)
    releases[1]()
    await pending
    expect(store.view).toBe('result')
    expect(store.generating).toBe(false)
    expect(store.papers).toHaveLength(2)
  })

  it('生成全部失败时留在搭建页，查询取得原结果后再切换', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('上游超时', 504))
    await store.generate()
    expect(store.view).toBe('build')
    expect(store.generateError).toBe('上游超时')
    expect(store.failedCount).toBe(1)
    const [params, requestId] = vi.mocked(api.generateBatch).mock.calls[0]
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({
      request_id: requestId!, status: 'succeeded', result: { sections: result(params) },
      error_status: 0, cache_expired: false,
    })
    await store.recoverPending()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.view).toBe('result')
    expect(store.papers).toHaveLength(1)
  })

  it.each(['whole', 'section', 'question'])('does not send %s generation when draft persistence fails', async mode => {
    const store = ready()
    const section = store.sections[0]
    section.data = { questions: [{ _qid: 'old-q', stem: '原题', answer: '原答案' }] }
    vi.mocked(store.flushDraft).mockResolvedValue(false)
    if (mode === 'whole') await store.generate()
    else if (mode === 'section') await store.retrySection(section.id)
    else await expect(store.replaceQuestion(section.id, 'old-q')).rejects.toThrow('未发送付费请求')
    expect(api.generateBatch).not.toHaveBeenCalled()
    expect(section.data.questions[0].stem).toBe('原题')
  })

  it('blocks a first request before persistence is ready', async () => {
    const store = ready(); store.persistenceReady = false
    await store.generate()
    expect(api.generateBatch).not.toHaveBeenCalled()
  })

  it('groups by total questions and splits a truncated section only on manual retry', async () => {
    const store = ready(); store.sections[0].count = 30
    store.addSection('fill_blank', 8)
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => result(params))
      .mockRejectedValueOnce(new api.ApiError('达到输出上限', 422, 'generation_truncated'))
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    await store.retryFailed()
    const calls = vi.mocked(api.generateBatch).mock.calls
    expect(calls.map(([params]) => params.items.reduce((sum, item) => sum + item.question_count, 0))).toEqual([30, 8, 4, 4])
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([30, 8])
  })

  it('rejects duplicate section IDs from a single provider response', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockImplementation(async params => [...result(params), ...result(params)])
    await store.generate()
    expect(store.papers).toHaveLength(0)
    expect(store.generateError).toContain('没有可用题目')
  })

  it('preserves complete sections in a truncated response and retries only unfinished sections', async () => {
    const store = ready(); store.addSection('fill_blank', 6)
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => {
      throw new api.ApiError('达到输出上限', 422, 'generation_truncated', '', result(params).slice(0, 1))
    })
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.pendingRun!.jobs[0].chunks[0].result?.[0].questions).toHaveLength(4)
    await store.retryFailed()
    const calls = vi.mocked(api.generateBatch).mock.calls
    expect(calls.map(([params]) => params.items.map(item => item.question_count))).toEqual([[4, 6], [6]])
    expect(calls[1][0].previous_request_ids).toEqual([calls[0][1]])
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([4, 6])
  })

  it('截断到只剩一题时再次补齐会原样重发，不再静默卡住', async () => {
    const store = ready()
    vi.mocked(api.generateBatch)
      .mockImplementationOnce(async params => {
        const partial = result(params).map(section => ({ ...section, questions: section.questions.slice(0, 3), missing_count: 1 }))
        throw new api.ApiError('缺题', 422, 'generation_incomplete', '', partial)
      })
      .mockRejectedValueOnce(new api.ApiError('达到输出上限', 422, 'generation_truncated'))
    await store.generate()
    await store.retryFailed()
    expect(vi.mocked(api.generateBatch).mock.calls.map(([params]) => params.items.map(item => item.question_count))).toEqual([[4], [1]])
    expect(store.failedCount).toBe(1)
    await store.retryFailed()
    const calls = vi.mocked(api.generateBatch).mock.calls
    expect(calls).toHaveLength(3)
    expect(calls[2][0].items.map(item => item.question_count)).toEqual([1])
    expect(store.sections[0].data?.questions).toHaveLength(4)
    expect(store.failedCount).toBe(0)
  })

  it.each(['retry', 'recover'])('retains truncated sections found during %s status lookup', async mode => {
    const store = ready(); store.addSection('fill_blank', 6)
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Network', 0))
    await store.generate()
    const [params, requestId] = vi.mocked(api.generateBatch).mock.calls[0]
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({ request_id: requestId!, status: 'failed', result: null,
      error: { code: 'generation_truncated', error: '达到输出上限', partial_sections: result(params).slice(0, 1) }, error_status: 422, cache_expired: false })
    if (mode === 'recover') {
      await store.recoverPending()
      expect(api.generateBatch).toHaveBeenCalledOnce()
      expect(store.pendingRun!.jobs[0].chunks[0].result?.[0].questions).toHaveLength(4)
    }
    await store.retryFailed()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.generateBatch).mock.calls[1][0].items.map(item => item.question_count)).toEqual([6])
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([4, 6])
  })

  it('uses all validated sections when only the final JSON wrapper was truncated', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => {
      throw new api.ApiError('达到输出上限', 422, 'generation_truncated', '', result(params))
    })
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.papers[0].sections[0].data.questions).toHaveLength(4)
    expect(store.failedCount).toBe(0)
  })

  it('keeps repeated 4 + 6 sections independent even when responses are reordered', async () => {
    const store = ready()
    store.addSection('fill_blank', 6)
    vi.mocked(api.generateBatch).mockImplementation(async params => result(params).reverse())
    await store.generate()
    const sent = vi.mocked(api.generateBatch).mock.calls[0][0]
    expect(sent.items.map(item => item.question_count)).toEqual([4, 6])
    expect(new Set(sent.items.map(item => item.section_id)).size).toBe(2)
    expect(store.papers[0].sections.map(section => section.data.questions.length)).toEqual([4, 6])
    store.papers[0].sections[0].data.questions[0].stem = 'Edited'
    expect(store.sections[0].data!.questions[0].stem).not.toBe('Edited')
    expect(store.papers[0].sections[1].data.questions[0].stem).not.toBe('Edited')
  })

  it('preserves the reading passage and the requested count on a short response', async () => {
    const store = ready()
    store.sections = []
    store.addSection('reading', 4)
    vi.mocked(api.generateBatch).mockImplementation(async params => result(params).map(section => ({ ...section, questions: section.questions.slice(0, 2), missing_count: 2, quality_warnings: ['请求 4 道，保留 2 道，缺少 2 道；补题有次数上限', '第 1 道题需核对答案'] })))
    await store.generate()
    expect(store.sections[0].count).toBe(4)
    expect(store.papers[0].sections[0].data.passage).toBe('Original passage')
    expect(store.papers[0].sections[0].warn).toContain('缺少 2 道')
    expect(store.papers[0].sections[0].warn?.match(/缺少 2 道/g)).toHaveLength(1)
    expect(store.papers[0].sections[0].warn).toContain('第 1 道题需核对答案')
    expect(store.generateWarn).toContain('缺题')
  })

  it('splits more than ten repeated sections without dropping any sections', async () => {
    const store = ready()
    for (let i = 1; i < 12; i++) store.addSection('fill_blank', 2)
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.generateBatch).mock.calls.map(([params]) => params.items.length)).toEqual([10, 2])
    expect(store.papers[0].sections).toHaveLength(12)
  })

  it('uses immutable generation conditions and layout', async () => {
    const store = ready()
    let resolve!: (value: api.BatchRespSection[]) => void
    vi.mocked(api.generateBatch).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const promise = store.generate()
    await vi.waitFor(() => expect(api.generateBatch).toHaveBeenCalledOnce())
    const params = vi.mocked(api.generateBatch).mock.calls[0][0]
    store.title = 'New title'; store.keyword = 'Changed'; store.sections[0].layout.qCols = 5
    resolve(result(params))
    await promise
    expect(store.papers[0].title).toBe('Original title')
    expect(store.papers[0].keyword).toBe('加法')
    expect(store.papers[0].sections[0].layout.qCols).not.toBe(5)
  })

  it('never creates a successful empty paper', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockResolvedValue([])
    await store.generate()
    expect(store.papers).toHaveLength(0)
    expect(store.failedCount).toBe(1)
    expect(store.generateError).toContain('空试卷')
  })
})

describe('uncertain requests and manual retries', () => {
  it('never sends a single-section request when query-only recovery has no request record', async () => {
    const store = ready()
    await store.retrySection(store.sections[0].id, 'recover')
    expect(api.generateBatch).not.toHaveBeenCalled()
    expect(api.fetchGenerationStatus).not.toHaveBeenCalled()
    expect(store.sections[0].error).toContain('未发送新请求')
    expect(store.sections[0].pendingGeneration).toBeUndefined()
  })

  it('persists a single-section request and recovers it without generating twice', async () => {
    const store = ready()
    const section = store.sections[0]
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Timeout', 504))
    await store.retrySection(section.id)
    expect(section.pendingGeneration).toBeDefined()
    expect(section.status).toBe('error')
    const [params, requestId] = vi.mocked(api.generateBatch).mock.calls[0]
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({ request_id: requestId!, status: 'succeeded', result: { sections: result(params) }, error_status: 0, cache_expired: false })
    await store.retrySection(section.id, 'recover')
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(section.status).toBe('ready')
    expect(section.pendingGeneration).toBeUndefined()
  })

  it('does not automatically retry a timeout and can recover the original response', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Timed out', 504))
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    const [params, requestId] = vi.mocked(api.generateBatch).mock.calls[0]
    expect(store.pendingRun!.jobs[0].chunks[0].requestId).toBe(requestId)
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({ request_id: requestId!, status: 'succeeded', result: { sections: result(params) }, error_status: 0, cache_expired: false })
    await store.recoverPending()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.papers).toHaveLength(1)
    expect(store.failedCount).toBe(0)
  })

  it('manual retry uses old conditions and a fresh ID without touching completed chunks', async () => {
    const store = ready()
    for (let i = 1; i < 12; i++) store.addSection('fill_blank', 2)
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => result(params)).mockRejectedValueOnce(new api.ApiError('Timed out', 504))
    await store.generate()
    expect(api.generateBatch).toHaveBeenCalledTimes(2)
    const oldId = vi.mocked(api.generateBatch).mock.calls[1][1]
    store.grade = '小学四年级'; store.keyword = 'New topic'; store.sections = []
    await store.retryFailed()
    expect(api.generateBatch).toHaveBeenCalledTimes(3)
    const [params, newId] = vi.mocked(api.generateBatch).mock.calls[2]
    expect(params.items).toHaveLength(2)
    expect(params.grade).toBe('小学三年级')
    expect(params.keyword).toBe('加法')
    expect(newId).not.toBe(oldId)
    expect(store.papers[0].sections).toHaveLength(12)
  })

  it('manual retry refuses to resend a request which is still running', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Network', 0))
    await store.generate()
    vi.mocked(api.fetchGenerationStatus).mockResolvedValueOnce({ request_id: 'old', status: 'running', result: null, error_status: 0, cache_expired: false })
    await store.retryFailed()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.failedCount).toBe(1)
    expect(store.generateError).toContain('处理中')
  })

  it('query-only recovery never issues a new model request on failure', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Network', 0))
    await store.generate()
    await store.recoverPending()
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.pendingRun).not.toBeNull()
  })

  it('does not replace an unfinished request when the recovery copy cannot be saved', async () => {
    const store = ready()
    vi.mocked(api.generateBatch).mockRejectedValueOnce(new api.ApiError('Timeout', 504))
    await store.generate()
    const requestId = store.pendingRun!.jobs[0].chunks[0].requestId
    store.persistenceReady = true
    store.ownerId = '1'
    const save = vi.spyOn(store, 'saveHistory').mockResolvedValueOnce(false)
    await store.generate()
    expect(save).toHaveBeenCalledWith('before-generate')
    expect(store.pendingRun!.jobs[0].chunks[0].requestId).toBe(requestId)
    expect(api.generateBatch).toHaveBeenCalledOnce()
    expect(store.generating).toBe(false)
  })

  it('removes completed jobs from recovery snapshots immediately', async () => {
    const store = ready()
    store.paperCount = 2
    let resolve!: (value: api.BatchRespSection[]) => void
    vi.mocked(api.generateBatch).mockImplementationOnce(async params => result(params)).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const promise = store.generate()
    await vi.waitFor(() => expect(store.papers).toHaveLength(1))
    expect(store.captureSnapshot().pendingRun!.jobs).toHaveLength(1)
    resolve(result(vi.mocked(api.generateBatch).mock.calls[1][0]))
    await promise
    expect(store.papers).toHaveLength(2)
  })
})
