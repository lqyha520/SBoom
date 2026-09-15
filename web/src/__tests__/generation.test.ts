import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as api from '../api'
import { useExamStore } from '../stores/exam'

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  generateBatch: vi.fn(),
  fetchGenerationUsage: vi.fn().mockResolvedValue(null),
  fetchGenerationStatus: vi.fn(),
}))

function ready() {
  const store = useExamStore()
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
    vi.mocked(api.generateBatch).mockImplementation(async params => result(params).map(section => ({ ...section, questions: section.questions.slice(0, 2), missing_count: 2 })))
    await store.generate()
    expect(store.sections[0].count).toBe(4)
    expect(store.papers[0].sections[0].data.passage).toBe('Original passage')
    expect(store.papers[0].sections[0].warn).toContain('缺少 2 道')
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
