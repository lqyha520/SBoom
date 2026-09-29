import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'

afterEach(() => { api.bindWorkspaceOwner(''); vi.unstubAllGlobals() })
const params: api.BatchParams = { grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', items: [{ section_id: 'one', game_type: 'fill_blank', question_count: 2 }] }

describe('request identity', () => {
  it('guards multi-step work against account changes', () => {
    api.bindWorkspaceOwner('17')
    const assertOwner = api.captureWorkspaceGuard()
    expect(assertOwner).not.toThrow()
    api.bindWorkspaceOwner('18')
    expect(assertOwner).toThrow(api.ApiError)
  })
  it('sends both the request ID and authenticated workspace owner', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sections: [] })))
    vi.stubGlobal('fetch', fetch)
    api.bindWorkspaceOwner('17')
    await api.generateBatch(params, 'test-request')
    const headers = fetch.mock.calls[0][1].headers as Headers
    expect(headers.get('X-Request-ID')).toBe('test-request')
    expect(headers.get('X-Workspace-User')).toBe('17')
  })

  it('does not retry timed-out HTTP requests', async () => {
    const fetch = vi.fn().mockRejectedValue(new DOMException('Timeout', 'TimeoutError'))
    vi.stubGlobal('fetch', fetch)
    await expect(api.generateBatch(params, 'original')).rejects.toMatchObject({ status: 0, requestId: 'original', code: 'network_unknown' })
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('passes validated partial sections through a truncation error without retrying', async () => {
    const sections = [{ section_id: 'one', game_type: 'fill_blank', questions: [{ stem: '1+1=__', answer: '2' }] }]
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: {
      error: '达到输出上限', code: 'generation_truncated', partial_sections: sections,
    } }), { status: 422 }))
    vi.stubGlobal('fetch', fetch)
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
    vi.stubGlobal('fetch', fetch)
    await expect(api.generateBatch(params, 'body-interrupted')).rejects.toMatchObject({
      status: 0, code: 'network_unknown', requestId: 'body-interrupted',
    })
    expect(fetch).toHaveBeenCalledOnce()
  })
})
