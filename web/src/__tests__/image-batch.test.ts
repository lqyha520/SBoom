import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { useImageBatch } from '../image-batch'
import { fetchImageStatus, generateWorksheetImage, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'

vi.mock('../image-generation', async original => ({ ...await original<typeof import('../image-generation')>(), generateWorksheetImage: vi.fn(), fetchImageStatus: vi.fn() }))
const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '加减法', difficulty: 'medium', items: [{ game_type: 'quiz', question_count: 4 }], style: 'clean', requirements: '' }
const image = (id: string): WorksheetImage => ({ request_id: id, b64_json: btoa('fixture'), mime_type: 'image/png', width: 2, height: 3, prompt: 'test' })
const generate = vi.mocked(generateWorksheetImage), query = vi.mocked(fetchImageStatus)
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear()
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  generate.mockImplementation(async (_, id) => image(id))
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

it('存储不可用时不发送付费请求，恢复后重用尚未发送的 ID', async () => {
  const failure = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
  const batch = useImageBatch('quota', () => true, () => {})
  await batch.start(params, 1)
  const id = batch.state.pages[0].id
  expect(generate).not.toHaveBeenCalled()
  expect(batch.state.pages[0].state).toBe('queued')
  expect(batch.storageError).toContain('暂未发送')
  failure.mockRestore()
  await batch.run()
  expect(generate).toHaveBeenCalledExactlyOnceWith(expect.anything(), id)
  expect(batch.completed).toBe(1)
  batch.dispose()
})

it('批次中途保存失败时保留已完成图片，重试只发送剩余页面', async () => {
  const setItem = localStorage.setItem.bind(localStorage)
  let blocked = true
  vi.spyOn(localStorage, 'setItem').mockImplementation((key, value) => {
    if (blocked && generate.mock.calls.length === 1) throw new Error('Full')
    setItem(key, value)
  })
  const batch = useImageBatch('quota-middle', () => true, () => {})
  await batch.start(params, 2)
  const id = batch.state.pages[1].id
  expect(generate).toHaveBeenCalledTimes(1)
  expect(batch.completed).toBe(1)
  blocked = false
  await batch.run()
  expect(generate).toHaveBeenCalledTimes(2)
  expect(generate.mock.calls[1][1]).toBe(id)
  expect(batch.completed).toBe(2)
  batch.dispose()
})

it('queries the original image after an unclassified response error before allowing another paid request', async () => {
  generate.mockRejectedValueOnce(new TypeError('response disconnected'))
  const batch = useImageBatch('body-disconnect', () => true, () => {})
  await batch.start(params, 1)
  const id = batch.state.pages[0].id
  expect(batch.unresolved).toBe(true)
  expect(batch.canContinue).toBe(false)
  await batch.run()
  expect(generate).toHaveBeenCalledOnce()
  query.mockResolvedValue({ kind: 'image', status: 'succeeded', result: image(id) } as Awaited<ReturnType<typeof fetchImageStatus>>)
  await batch.recover()
  expect(query).toHaveBeenCalledWith(id, expect.any(AbortSignal))
  expect(batch.completed).toBe(1)
  expect(batch.state.pages[0].id).toBe(id)
  expect(generate).toHaveBeenCalledOnce()
  batch.dispose()
})

it('generates each page once, in order, keeping every selected condition and separate request IDs', async () => {
  const shown = vi.fn(), batch = useImageBatch('batch', () => true, shown)
  expect(batch.canContinue).toBe(false) // The component reads this during its initial render.
  await batch.start(params, 3)
  expect(generate.mock.calls.map(([body]) => body)).toEqual([1, 2, 3].map(image_index => ({ ...params, image_count: 3, image_index })))
  expect(new Set(generate.mock.calls.map(([, id]) => id)).size).toBe(3)
  expect(batch.completed).toBe(3); expect(batch.canContinue).toBe(false)
  expect(shown.mock.calls).toEqual([[0], [1], [2]])
  expect(localStorage.getItem('batch')).not.toContain('b64_json')
  batch.dispose(); expect(URL.revokeObjectURL).toHaveBeenCalledTimes(3)
})

it('stops on timeout, preserves earlier results, queries before resuming and never automatically retries a paid call', async () => {
  generate.mockImplementationOnce(async (_, id) => image(id)).mockRejectedValueOnce(new ApiError('timeout', 504))
  const batch = useImageBatch('batch', () => true, () => {})
  await batch.start(params, 3)
  expect(batch.completed).toBe(1); expect(generate).toHaveBeenCalledTimes(2)
  expect(batch.unresolved).toBe(true); expect(batch.canContinue).toBe(false)
  await batch.run(); expect(generate).toHaveBeenCalledTimes(2)
  const failedId = batch.state.pages[1].id
  query.mockResolvedValue({ kind: 'image', status: 'unknown', result: null, cache_expired: false } as Awaited<ReturnType<typeof fetchImageStatus>>)
  await batch.recover()
  expect(query).toHaveBeenCalledWith(failedId, expect.any(AbortSignal)); expect(generate).toHaveBeenCalledTimes(2)
  expect(batch.state.pages[1].error).toContain('费用')
  await batch.run()
  expect(generate).toHaveBeenCalledTimes(4); expect(batch.completed).toBe(3)
  expect(generate.mock.calls[2][1]).not.toBe(failedId)
  expect(generate.mock.calls[2][0].image_index).toBe(2)
  batch.dispose()
})

it('pauses after the current image, and reload queries completed pages without generating queued ones', async () => {
  let complete!: (value: WorksheetImage) => void
  generate.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const batch = useImageBatch('batch', () => true, () => {})
  const started = batch.start(params, 3)
  batch.pause(); complete(image(batch.state.pages[0].id)); await started
  expect(generate).toHaveBeenCalledTimes(1); expect(batch.completed).toBe(1)
  const ids = batch.state.pages.map(page => page.id)
  query.mockImplementation(async id => ({ kind: 'image', status: 'succeeded', result: image(id) } as Awaited<ReturnType<typeof fetchImageStatus>>))
  batch.dispose()
  const restored = useImageBatch('batch', () => true, () => {})
  await restored.restore()
  expect(generate).toHaveBeenCalledTimes(1); expect(query).toHaveBeenCalledTimes(1)
  expect(restored.completed).toBe(1); expect(restored.canContinue).toBe(true)
  await restored.run()
  expect(generate.mock.calls.map(([, id]) => id)).toEqual(ids)
  expect(restored.completed).toBe(3); restored.dispose()
})

it('reload recovers every completed image and keeps a still-running page blocked', async () => {
  localStorage.setItem('batch', JSON.stringify({ version: 1, input: params, pages: [{ id: 'first', state: 'ready' }, { id: 'second', state: 'running' }] }))
  query.mockImplementation(async id => ({ kind: 'image', status: id === 'first' ? 'succeeded' : 'running', result: id === 'first' ? image(id) : null } as Awaited<ReturnType<typeof fetchImageStatus>>))
  const batch = useImageBatch('batch', () => true, () => {})
  await batch.restore(); expect(batch.completed).toBe(1); expect(batch.unresolved).toBe(true)
  await batch.run(); expect(generate).not.toHaveBeenCalled(); batch.dispose()
})

it('supports an older single-image request and ignores malformed or oversized saved batches', async () => {
  query.mockResolvedValue({ kind: 'image', status: 'succeeded', result: image('old-request') } as Awaited<ReturnType<typeof fetchImageStatus>>)
  localStorage.setItem('batch', 'old-request')
  const old = useImageBatch('batch', () => true, () => {}); await old.restore()
  expect(old.completed).toBe(1); old.dispose(); query.mockClear()
  for (const raw of ['{', JSON.stringify({ version: 1, pages: Array.from({ length: 11 }, (_, i) => ({ id: 'page-' + i, state: 'ready' })) })]) {
    localStorage.setItem('batch', raw)
    const batch = useImageBatch('batch', () => true, () => {}); await batch.restore()
    expect(batch.state.pages).toHaveLength(0); batch.dispose()
  }
  expect(generate).not.toHaveBeenCalled(); expect(query).not.toHaveBeenCalled()
})

it('does not continue the batch or expose images after the account changes', async () => {
  let active = true, finish!: (value: WorksheetImage) => void
  generate.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const shown = vi.fn(), batch = useImageBatch('batch', () => active, shown)
  const task = batch.start(params, 3); active = false; batch.dispose()
  finish(image('one')); await task
  expect(generate).toHaveBeenCalledTimes(1); expect(shown).not.toHaveBeenCalled()
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})

it('bounds the requested count before sending requests', async () => {
  const batch = useImageBatch('batch', () => true, () => {})
  for (const count of [0, 11, 1.5]) await expect(batch.start(params, count)).rejects.toThrow('1 至 10')
  expect(generate).not.toHaveBeenCalled(); batch.dispose()
})

it('keeps a completed paid request recoverable when its separate file download fails', async () => {
  const nativeFetch = globalThis.fetch
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: 'file unavailable' } }), { status: 503 }))
  try {
    generate.mockImplementation(async (_, id) => ({ ...image(id), b64_json: undefined, url: '/api/v1/image-generation/assets/' + 'a'.repeat(32) }))
    const batch = useImageBatch('file-failure', () => true, () => {})
    await batch.start(params, 1)
    expect(batch.state.pages[0].state).toBe('unknown')
    expect(batch.canContinue).toBe(false)
    await batch.run()
    expect(generate).toHaveBeenCalledTimes(1)
    query.mockImplementation(async id => ({ kind: 'image', status: 'succeeded', result: image(id) } as Awaited<ReturnType<typeof fetchImageStatus>>))
    await batch.recover()
    expect(batch.completed).toBe(1)
    expect(generate).toHaveBeenCalledTimes(1)
    batch.dispose()
  } finally { globalThis.fetch = nativeFetch }
})

it('断线后自动查询原请求，逐步降低频率，找回图片后不自动生成下一张', async () => {
  vi.useFakeTimers()
  generate.mockRejectedValueOnce(new ApiError('网络中断', 0))
  const batch = useImageBatch('auto-recover', () => true, () => {})
  try {
    await batch.start(params, 2)
    const id = batch.state.pages[0].id
    query.mockResolvedValueOnce({ kind: 'image', status: 'running', result: null } as Awaited<ReturnType<typeof fetchImageStatus>>)
      .mockResolvedValueOnce({ kind: 'image', status: 'succeeded', result: image(id) } as Awaited<ReturnType<typeof fetchImageStatus>>)
    await vi.advanceTimersByTimeAsync(4_999)
    expect(query).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(query).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(9_999)
    expect(query).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(query).toHaveBeenCalledTimes(2)
    expect(batch.completed).toBe(1)
    expect(batch.canContinue).toBe(true)
    await vi.advanceTimersByTimeAsync(120_000)
    expect(query).toHaveBeenCalledTimes(2)
    expect(generate).toHaveBeenCalledTimes(1)
    expect(batch.state.pages[1].state).toBe('queued')
  } finally { batch.dispose() }
})

it('后台和离线暂停自动查询，回到页面后继续；销毁后移除监听和计时器', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  generate.mockRejectedValueOnce(new ApiError('网络中断', 0))
  query.mockResolvedValue({ kind: 'image', status: 'running', result: null } as Awaited<ReturnType<typeof fetchImageStatus>>)
  const batch = useImageBatch('background-recover', () => true, () => {})
  try {
    await batch.start(params, 1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(query).not.toHaveBeenCalled()
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(0)
    expect(query).toHaveBeenCalledTimes(1)
    online.mockReturnValue(false)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(query).toHaveBeenCalledTimes(1)
    online.mockReturnValue(true)
    window.dispatchEvent(new Event('online'))
    await vi.advanceTimersByTimeAsync(0)
    expect(query).toHaveBeenCalledTimes(2)
  } finally { batch.dispose() }
  window.dispatchEvent(new Event('online'))
  document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(60_000)
  expect(query).toHaveBeenCalledTimes(2)
  expect(query.mock.calls[0][1]?.aborted).toBe(true)
})

it('自动查询有次数上限，达到上限后仍可手动找回，不重发生成', async () => {
  vi.useFakeTimers()
  generate.mockRejectedValueOnce(new ApiError('网络中断', 0))
  query.mockRejectedValue(new ApiError('暂时无法查询', 503))
  const batch = useImageBatch('bounded-recover', () => true, () => {})
  try {
    await batch.start(params, 1)
    await vi.runAllTimersAsync()
    expect(query).toHaveBeenCalledTimes(120)
    expect(generate).toHaveBeenCalledTimes(1)
    expect(batch.canContinue).toBe(false)
    query.mockResolvedValue({ kind: 'image', status: 'succeeded', result: image(batch.state.pages[0].id) } as Awaited<ReturnType<typeof fetchImageStatus>>)
    await batch.recover()
    expect(batch.completed).toBe(1)
  } finally { batch.dispose() }
})

it('心跳过期的未知结果不自动重发，显式重试前保留费用提示', async () => {
  vi.useFakeTimers()
  generate.mockRejectedValueOnce(new ApiError('网络中断', 0))
  const batch = useImageBatch('lease-pending', () => true, () => {})
  try {
    await batch.start(params, 1)
    query.mockResolvedValue({ kind: 'image', status: 'unknown', result: null,
      error: { code: 'generation_lease_expired', error: '任务心跳超时，结果尚不确定' }, error_status: 0,
    } as Awaited<ReturnType<typeof fetchImageStatus>>)
    await batch.recover()
    expect(batch.state.pages[0].error).toContain('再次生成可能产生新的费用')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(generate).toHaveBeenCalledTimes(1)
  } finally { batch.dispose() }
})

it('查询过程中离开页面会取消只读请求，晚到结果不创建图片或继续轮询', async () => {
  let finish!: (value: Awaited<ReturnType<typeof fetchImageStatus>>) => void
  generate.mockRejectedValueOnce(new ApiError('网络中断', 0))
  query.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const batch = useImageBatch('dispose-recover', () => true, () => {})
  await batch.start(params, 1)
  const recovering = batch.recover()
  await vi.waitFor(() => expect(query).toHaveBeenCalledTimes(1))
  batch.dispose()
  expect(query.mock.calls[0][1]?.aborted).toBe(true)
  finish({ kind: 'image', status: 'succeeded', result: image(batch.state.pages[0].id) } as Awaited<ReturnType<typeof fetchImageStatus>>)
  await recovering
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})
