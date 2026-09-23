import { afterEach, expect, it, vi } from 'vitest'
import { bindWorkspaceOwner } from '../api'
import { addImagePublication, type ImagePublicationMeta } from '../image-publication'

const meta: ImagePublicationMeta = { title: '加减法 & 练习', grade: '小学三年级', subject: '数学', category_id: 'practice', description: '两页习题' }
afterEach(() => { bindWorkspaceOwner(''); vi.unstubAllGlobals() })

it('uploads the PDF directly to the existing draft import endpoint with owner identity and student mode', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'draft', status: 'draft' })))
  vi.stubGlobal('fetch', fetch); bindWorkspaceOwner('17')
  const pdf = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
  expect(await addImagePublication(pdf, meta)).toMatchObject({ id: 'draft', status: 'draft' })
  const [url, options] = fetch.mock.calls[0]
  const parsed = new URL(url, 'http://localhost')
  expect(parsed.pathname).toBe('/api/v1/admin/catalog/import')
  expect(Object.fromEntries(parsed.searchParams)).toEqual({ ...meta, mode: 'student', download_mode: 'pdf', view_access: 'inherit', download_access: 'inherit' })
  expect(options.body).toBe(pdf)
  expect(options.headers.get('Content-Type')).toBe('application/pdf')
  expect(options.headers.get('X-Workspace-User')).toBe('17')
  expect(fetch).toHaveBeenCalledOnce()
})

it('rejects oversized PDFs before uploading and never retries a request with an unknown result', async () => {
  const fetch = vi.fn().mockRejectedValue(new DOMException('timeout', 'TimeoutError'))
  vi.stubGlobal('fetch', fetch)
  const pdf = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
  const oversized = new Blob(['large'], { type: 'application/pdf' })
  Object.defineProperty(oversized, 'size', { value: 32 * 1024 * 1024 + 1 })
  expect(() => addImagePublication(oversized, meta)).toThrow('32 MB')
  expect(fetch).not.toHaveBeenCalled()
  await expect(addImagePublication(pdf, meta)).rejects.toMatchObject({ code: 'network_unknown' })
  expect(fetch).toHaveBeenCalledOnce()
})
