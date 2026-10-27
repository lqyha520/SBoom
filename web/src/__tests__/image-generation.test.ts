import { afterEach, describe, expect, it, vi } from 'vitest'
import { bindWorkspaceOwner } from '../api'
import { fetchImageStatus, generateWorksheetImage, imageBlob, loadImageBlob, MAX_IMAGE_BYTES, plannedImageQuestionCount, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'

function stubFetch(mock: typeof fetch) {
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => String(input).startsWith('/api/v1/generation/options')
    ? Promise.resolve(new Response(JSON.stringify({ revision: 'images-v1', timeout_ms: 1500000, task_timeout_seconds: 1470 })))
    : mock(input, init))
}

const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '两位数加减法', difficulty: 'medium', items: [{ game_type: 'fill_blank', question_count: 4 }], style: 'black_white', requirements: '预留书写空间' }
afterEach(() => { bindWorkspaceOwner(''); vi.unstubAllGlobals() })

describe('image worksheets', () => {
  it('only reports a planned total when every selected type has an explicit quantity', () => {
    expect(plannedImageQuestionCount([])).toBeUndefined()
    expect(plannedImageQuestionCount([{ game_type: 'quiz' }])).toBeUndefined()
    expect(plannedImageQuestionCount([{ game_type: 'quiz', question_count: null }])).toBeUndefined()
    expect(plannedImageQuestionCount([{ game_type: 'quiz', question_count: 4 }, { game_type: 'fill_blank' }])).toBeUndefined()
    expect(plannedImageQuestionCount([{ game_type: 'quiz', question_count: 4 }, { game_type: 'fill_blank', question_count: 6 }])).toBe(10)
  })
  it('sends automatic quantities without substituting a default count', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    stubFetch(fetch)
    const automatic = { ...params, items: [{ game_type: 'quiz', question_count: null }, { game_type: 'fill_blank' }] }
    await generateWorksheetImage(automatic, 'automatic')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(automatic)
  })
  it('sends the selected content with request and account identity, without paper layout', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ request_id: 'image-1' })))
    stubFetch(fetch); bindWorkspaceOwner('17')
    await generateWorksheetImage(params, 'image-1')
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/v1/generate-image')
    expect(JSON.parse(options.body)).toEqual(params)
    expect(options.headers.get('X-Request-ID')).toBe('image-1')
    expect(options.headers.get('X-Workspace-User')).toBe('17')
    expect(options.headers.get('X-Model-Config-Revision')).toBe('images-v1')
  })
  it('previews the prompt and recovers a request using separate non-generating endpoints', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
    stubFetch(fetch)
    await previewImagePrompt(params); await fetchImageStatus('image-1')
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/image-generation/prompt')
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/me/generations/image-1')
    expect(fetch.mock.calls[1][1].method).toBeUndefined()
  })
  it('does not retry a timed-out image call', async () => {
    const fetch = vi.fn().mockRejectedValue(new DOMException('Timeout', 'TimeoutError'))
    stubFetch(fetch)
    await expect(generateWorksheetImage(params, 'original-image')).rejects.toMatchObject({ requestId: 'original-image', code: 'network_unknown' })
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('creates a locally downloadable PNG and rejects unknown MIME types', async () => {
    const image: WorksheetImage = { request_id: 'one', b64_json: btoa('PNG fixture'), mime_type: 'image/png', width: 1, height: 1, prompt: 'prompt' }
    const blob = imageBlob(image)
    expect(blob.type).toBe('image/png'); expect(blob.size).toBe(11)
    expect(() => imageBlob({ ...image, mime_type: 'image/svg+xml' as 'image/png' })).toThrow()
    expect(() => imageBlob({ ...image, b64_json: '' })).toThrow()
    expect(() => imageBlob({ ...image, b64_json: undefined, blob: new Blob([], { type: 'image/png' }) })).toThrow()
    expect(() => imageBlob({ ...image, b64_json: 'A'.repeat(4 * Math.ceil(MAX_IMAGE_BYTES / 3) + 4) })).toThrow()
  })
  it('可取消状态查询和图片下载，不再等待已离开的页面', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
    stubFetch(fetch)
    const controller = new AbortController()
    controller.abort()
    await expect(fetchImageStatus('cancelled', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    await expect(loadImageBlob({ url: '/api/v1/image-generation/assets/' + 'a'.repeat(32) } as WorksheetImage, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).not.toHaveBeenCalled()
  })
})
