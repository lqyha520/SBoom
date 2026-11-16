import { afterEach, expect, it, vi } from 'vitest'
import { bindWorkspaceOwner } from '../api'
import { imageCloudRequestId, saveImageArchive } from '../image-cloud'
import { addArchivePublication } from '../image-publication'
import type { ImageWorksheetParams, WorksheetImage } from '../image-generation'

const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '加减法', difficulty: 'medium', items: [{ game_type: 'quiz', question_count: 4 }], style: 'clean', requirements: '' }
const pdf = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
afterEach(() => { bindWorkspaceOwner(''); vi.unstubAllGlobals() })

it('uses the ordered batch identities as a stable key across reloads and distinguishes partial batches', async () => {
  const images = ['first', 'second'].map(request_id => ({ request_id } as WorksheetImage))
  const key = await imageCloudRequestId(images)
  expect(key).toMatch(/^[a-f0-9]{64}$/)
  expect(await imageCloudRequestId(structuredClone(images))).toBe(key)
  expect(await imageCloudRequestId(images.slice(0, 1))).not.toBe(key)
  expect(await imageCloudRequestId([...images].reverse())).not.toBe(key)
})

it('saves up to forty images and carries the complete question count', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetch)
  const images = Array.from({ length: 40 }, (_, index) => ({ request_id: 'page-' + index } as WorksheetImage))
  const key = await imageCloudRequestId(images)
  await saveImageArchive(pdf, key, '四十张练习', { ...params, items: [{ game_type: 'quiz', question_count: 20 }, { game_type: 'fill_blank', question_count: 4 }] }, 40, null)
  expect(new URL(fetch.mock.calls[0]![0], 'http://localhost').searchParams.get('question_count')).toBe('960')
  expect(() => saveImageArchive(pdf, key, '过大', params, 41, null)).toThrow('40')
})

it('uploads a private PDF with original metadata and an optional folder without publishing', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'cloud', file_status: 'ready' })))
  vi.stubGlobal('fetch', fetch); bindWorkspaceOwner('17')
  await saveImageArchive(pdf, 'a'.repeat(64), '练习 & 复习', params, 2, 'folder')
  const [url, options] = fetch.mock.calls[0]!
  const parsed = new URL(url, 'http://localhost')
  expect(parsed.pathname).toBe('/api/v1/library/import')
  expect(Object.fromEntries(parsed.searchParams)).toEqual({ request_id: 'a'.repeat(64), title: '练习 & 复习', grade: params.grade, subject: params.subject, keyword: params.keyword, question_types: 'quiz', question_count: '8', folder_id: 'folder' })
  expect(options.body).toBe(pdf)
  expect(options.headers.get('X-Workspace-User')).toBe('17')
  expect(fetch).toHaveBeenCalledOnce()
})

it('omits unspecified question counts and rejects oversized uploads before making a request', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetch)
  await saveImageArchive(pdf, 'a'.repeat(64), '自动题量', { ...params, items: [] }, 2, null)
  const query = new URL(fetch.mock.calls[0]![0], 'http://localhost').searchParams
  expect(query.has('question_count')).toBe(false)
  expect(query.has('folder_id')).toBe(false)
  const oversized = new Blob(['large'], { type: 'application/pdf' })
  Object.defineProperty(oversized, 'size', { value: 32 * 1024 * 1024 + 1 })
  expect(() => saveImageArchive(oversized, 'a'.repeat(64), '练习', params, 2, null)).toThrow('32 MB')
  expect(fetch).toHaveBeenCalledOnce()
})

it('creates a draft from the cloud archive ID instead of uploading another file', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'draft', status: 'draft' })))
  vi.stubGlobal('fetch', fetch); bindWorkspaceOwner('17')
  const meta = { title: '练习', category_id: 'practice', description: '' }
  await addArchivePublication('cloud', meta)
  const [url, options] = fetch.mock.calls[0]!
  expect(url).toBe('/api/v1/admin/catalog/papers')
  expect(JSON.parse(options.body)).toEqual({ paper_id: 'cloud', ...meta, download_mode: 'pdf', view_access: 'inherit', download_access: 'inherit' })
  expect(options.headers.get('X-Workspace-User')).toBe('17')
})
