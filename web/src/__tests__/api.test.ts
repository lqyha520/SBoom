import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'

function stubFetch(mock: typeof fetch) {
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => String(input).startsWith('/api/v1/generation/options')
    ? Promise.resolve(new Response(JSON.stringify({ revision: 'models-v1', timeout_ms: 900000, task_timeout_seconds: 870 })))
    : mock(input, init))
}

afterEach(() => { api.bindWorkspaceOwner(''); vi.unstubAllGlobals(); vi.restoreAllMocks() })
const params: api.BatchParams = { grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', items: [{ section_id: 'one', game_type: 'fill_blank', question_count: 2 }] }

describe('request identity', () => {
  it('读取后台等待时限并携带同一配置版本，600 秒模型不会被固定 300 秒提前截断', async () => {
    const deadlines: number[] = []
    vi.spyOn(AbortSignal, 'timeout').mockImplementation(ms => { deadlines.push(ms); return new AbortController().signal })
    const fetch = vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(
      url.includes('/generation/options') ? { revision: 'backend-version', timeout_ms: 690000, task_timeout_seconds: 660 } : { sections: [] },
    ))))
    vi.stubGlobal('fetch', fetch)
    await api.generateBatch(params, 'backend-timeout')
    expect(deadlines).toEqual([30000, 690000])
    expect(fetch.mock.calls[1][1].headers.get('X-Model-Config-Revision')).toBe('backend-version')
    expect(fetch.mock.calls[1][1].headers.get('X-Request-ID')).toBe('backend-timeout')
  })

  it('读取时限失败时不使用猜测值发送付费请求', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await expect(api.generateBatch(params)).rejects.toMatchObject({ code: 'model_policy_unavailable' })
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toContain('/generation/options')
  })

  it('生成请求始终使用后台时限，旧调用方传入的固定超时不再覆盖', async () => {
    const deadlines: number[] = []
    vi.spyOn(AbortSignal, 'timeout').mockImplementation(ms => { deadlines.push(ms); return new AbortController().signal })
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sections: [] })))
    stubFetch(fetch)
    await api.request('/api/v1/generate-batch', { method: 'POST' }, 300000)
    expect(deadlines).toEqual([30000, 900000])
    expect(fetch.mock.calls[0][1].headers.get('X-Model-Config-Revision')).toBe('models-v1')
  })

  it('读取配置期间账号变化时不再发送付费请求', async () => {
    api.bindWorkspaceOwner('17')
    const fetch = vi.fn().mockImplementation(() => {
      api.bindWorkspaceOwner('18')
      return Promise.resolve(new Response(JSON.stringify({ revision: 'v1', timeout_ms: 600000 })))
    })
    vi.stubGlobal('fetch', fetch)
    await expect(api.generateBatch(params)).rejects.toMatchObject({ code: 'account_changed' })
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('guards multi-step work against account changes', () => {
    api.bindWorkspaceOwner('17')
    const assertOwner = api.captureWorkspaceGuard()
    expect(assertOwner).not.toThrow()
    api.bindWorkspaceOwner('18')
    expect(assertOwner).toThrow(api.ApiError)
  })
  it('sends both the request ID and authenticated workspace owner', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sections: [] })))
    stubFetch(fetch)
    api.bindWorkspaceOwner('17')
    await api.generateBatch(params, 'test-request')
    const headers = fetch.mock.calls[0][1].headers as Headers
    expect(headers.get('X-Request-ID')).toBe('test-request')
    expect(headers.get('X-Workspace-User')).toBe('17')
  })

  it('发送本卷前序请求标识供服务端读取已完成的大题', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sections: [] })))
    stubFetch(fetch)
    await api.generateBatch({ ...params, previous_request_ids: ['completed-chunk'] }, 'next-chunk')
    expect(JSON.parse(fetch.mock.calls[0][1].body).previous_request_ids).toEqual(['completed-chunk'])
  })

  it('does not retry timed-out HTTP requests', async () => {
    const fetch = vi.fn().mockRejectedValue(new DOMException('Timeout', 'TimeoutError'))
    stubFetch(fetch)
    await expect(api.generateBatch(params, 'original')).rejects.toMatchObject({ status: 0, requestId: 'original', code: 'network_unknown' })
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('passes validated partial sections through a truncation error without retrying', async () => {
    const sections = [{ section_id: 'one', game_type: 'fill_blank', questions: [{ stem: '1+1=__', answer: '2' }] }]
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: {
      error: '达到输出上限', code: 'generation_truncated', partial_sections: sections,
    } }), { status: 422 }))
    stubFetch(fetch)
    await expect(api.generateBatch(params, 'partial')).rejects.toMatchObject({
      status: 422, code: 'generation_truncated', requestId: 'partial', partialSections: sections,
    })
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('distinguishes a template conflict from an ordinary network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: 'Conflict', code: 'template_conflict' } }), { status: 409 })))
    await expect(api.deleteTemplateOnServer('Template', 2)).rejects.toMatchObject({ status: 409, code: 'template_conflict' })
  })

  it('keeps the paid request identity when a 200 response body is interrupted', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.reject(new TypeError('terminated')) })
    stubFetch(fetch)
    await expect(api.generateBatch(params, 'body-interrupted')).rejects.toMatchObject({
      status: 0, code: 'network_unknown', requestId: 'body-interrupted',
    })
    expect(fetch).toHaveBeenCalledOnce()
  })
})
