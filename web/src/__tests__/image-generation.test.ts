import { afterEach, describe, expect, it, vi } from 'vitest'
import { bindWorkspaceOwner } from '../api'
import { fetchImageStatus, generateWorksheetImage, imageBlob, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'

const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '两位数加减法', difficulty: 'medium', items: [{ game_type: 'fill_blank', question_count: 4 }], style: 'black_white', requirements: '预留书写空间' }
afterEach(() => { bindWorkspaceOwner(''); vi.unstubAllGlobals() })

describe('image worksheets', () => {
  it('sends the selected content with request and account identity, without paper layout', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ request_id: 'image-1' })))
    vi.stubGlobal('fetch', fetch); bindWorkspaceOwner('17')
    await generateWorksheetImage(params, 'image-1')
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/v1/generate-image')
    expect(JSON.parse(options.body)).toEqual(params)
    expect(options.headers.get('X-Request-ID')).toBe('image-1')
    expect(options.headers.get('X-Workspace-User')).toBe('17')
  })
  it('previews the prompt and recovers a request using separate non-generating endpoints', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetch)
    await previewImagePrompt(params); await fetchImageStatus('image-1')
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/image-generation/prompt')
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/me/generations/image-1')
    expect(fetch.mock.calls[1][1].method).toBeUndefined()
  })
  it('does not retry a timed-out image call', async () => {
    const fetch = vi.fn().mockRejectedValue(new DOMException('Timeout', 'TimeoutError'))
    vi.stubGlobal('fetch', fetch)
    await expect(generateWorksheetImage(params, 'original-image')).rejects.toMatchObject({ requestId: 'original-image', code: 'network_unknown' })
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('creates a locally downloadable PNG and rejects unknown MIME types', async () => {
    const image: WorksheetImage = { request_id: 'one', b64_json: btoa('PNG fixture'), mime_type: 'image/png', width: 1, height: 1, prompt: 'prompt' }
    const blob = imageBlob(image)
    expect(blob.type).toBe('image/png'); expect(blob.size).toBe(11)
    expect(() => imageBlob({ ...image, mime_type: 'image/svg+xml' as 'image/png' })).toThrow()
    expect(() => imageBlob({ ...image, b64_json: '' })).toThrow()
  })
})
