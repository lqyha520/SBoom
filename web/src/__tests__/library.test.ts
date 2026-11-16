import { beforeEach, describe, expect, it, vi } from 'vitest'
import { bindWorkspaceOwner } from '../api'
import { archivePapers, captureCollection, captureSnapshot, completeArchive, createArchive, patchArchive } from '../library'
import type { ArchiveDetail, ArchiveRequest } from '../library'
import type { PaperData, PaperStyle } from '../types'
import { DEFAULT_LAYOUT, TEMPLATES } from '../constants'
import { createArchiveBundle } from '../exporter'

vi.mock('../exporter', () => ({ createArchiveBundle: vi.fn() }))

describe('cloud archive boundary', () => {
  const paper: PaperData = { archiveSourceId: 'source-test', title: '试卷', titleHtml: '<b>试卷</b>', grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium',
    day: 3, hiddenElements: ['reward'], footerOverride: '页脚', sections: [{ type: 'quiz', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '1 + 1', answer: 2, _stemHtml: '<b>1 + 1</b>' }] } }] }
  const style: PaperStyle = { bg: 'none', bgOpacity: 70, banner: false, secColor: false, frame: 'none', encourage: false, reward: false, kidFont: 'off', exportBg: false, titleScale: 1, titleOffsetY: 0 }
  beforeEach(() => { bindWorkspaceOwner('teacher-1'); vi.unstubAllGlobals(); vi.mocked(createArchiveBundle).mockReset() })
  it('captures a complete deep copy, independent of subsequent edits', () => {
    const copy = captureSnapshot(paper, TEMPLATES[0], style, 'withAnswers', false)
    expect(copy.paper.titleHtml).toBe(paper.titleHtml)
    expect(copy.paper.hiddenElements).toEqual(['reward'])
    expect(copy.paper.footerOverride).toBe('页脚')
    expect(copy.export_options).toEqual({ mode: 'withAnswers', addDay: false, renderer_version: 'web-v1' })
    expect(copy.template).toEqual(TEMPLATES[0])
    expect(copy.style).toEqual(style)
    copy.paper.sections[0].data.questions[0].stem = 'edited'
    copy.style.titleScale = 2
    expect(paper.sections[0].data.questions[0].stem).toBe('1 + 1')
    expect(style.titleScale).toBe(1)
  })
  it('sends owned archive requests separately from local drafts and generation', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'archive-1' }), { status: 201 }))
    vi.stubGlobal('fetch', fetch)
    const request: ArchiveRequest = { request_id: 'request-1', source_id: 'source-test', snapshot: captureSnapshot(paper, TEMPLATES[0], style, 'student', true), folder_id: null, group_id: '', group_name: '' }
    await createArchive(request)
    expect(fetch).toHaveBeenCalledOnce()
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/v1/library/papers')
    expect(options.headers.get('X-Workspace-User')).toBe('teacher-1')
    expect(JSON.parse(options.body)).toEqual(request)
  })
  it('captures all twenty papers with stable collection identity and independent snapshots', async () => {
    const papers = Array.from({ length: 20 }, (_, index) => ({ ...paper, archiveSourceId: 'source-' + index, title: '第' + index + '天' }))
    const first = await captureCollection(papers, TEMPLATES[0], style, 'withAnswers', true, '进位加法')
    expect(first.snapshot.collection_title).toBe('进位加法')
    expect(first.snapshot.export_options.renderer_version).toBe('web-v2')
    expect(archivePapers(first.snapshot)).toEqual(papers)
    const again = await captureCollection(papers, TEMPLATES[0], style, 'student', false, '新标题')
    expect(first.source_id).toBe(again.source_id)
    const reordered = await captureCollection([...papers].reverse(), TEMPLATES[0], style, 'student', false, '')
    expect(reordered.source_id).not.toBe(first.source_id)
    first.snapshot.additional_papers![0].sections[0].data.questions[0].stem = 'edited'
    expect(papers[1].sections[0].data.questions[0].stem).toBe('1 + 1')
    const record = { id: 'merged', file_status: 'pending', snapshot: again.snapshot } as ArchiveDetail
    vi.mocked(createArchiveBundle).mockResolvedValue(new Blob(['merged PDF and previews']))
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...record, file_status: 'ready' })))
    vi.stubGlobal('fetch', fetch)
    await completeArchive(record)
    expect(createArchiveBundle).toHaveBeenCalledWith(again.snapshot, undefined, expect.any(Object))
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/library/papers/merged/files')
  })
  it('keeps the original complete title as the default file name without numbering or truncation', async () => {
    const longTitle = '原'.repeat(240)
    const papers = [{ ...paper, title: longTitle }, { ...paper, title: '第二份自定标题' }]
    const { snapshot } = await captureCollection(papers, TEMPLATES[0], style, 'student', true, '')
    expect(snapshot.collection_title).toBe(longTitle)
    expect(archivePapers(snapshot)).toEqual(papers)
  })
  it('completed files are reused without rendering or fetching', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const ready = { id: 'archive-1', file_status: 'ready' } as ArchiveDetail
    expect(await completeArchive(ready)).toBe(ready)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('metadata updates do not include the snapshot', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await patchArchive('paper-id', { folder_id: null })
    expect(fetch.mock.calls[0][1].method).toBe('PUT')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ folder_id: null })
  })
  it('directs incomplete image uploads back to their source instead of rendering an empty paper', async () => {
    const record = { id: 'image-archive', file_status: 'pending', snapshot: { paper: { sections: [] } } } as unknown as ArchiveDetail
    await expect(completeArchive(record)).rejects.toThrow('请回到图片出题或原上传入口重试保存')
    expect(createArchiveBundle).not.toHaveBeenCalled()
  })
  it('does not upload a rendered paper into a changed account', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    vi.mocked(createArchiveBundle).mockImplementation(async () => {
      bindWorkspaceOwner('teacher-2')
      return new Blob(['private paper'])
    })
    const record = { id: 'archive-1', file_status: 'pending', snapshot: captureSnapshot(paper, TEMPLATES[0], style, 'student', true) } as ArchiveDetail
    await expect(completeArchive(record)).rejects.toMatchObject({ code: 'account_changed' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('a closed save dialog does not upload after rendering finishes', async () => {
    let active = true
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    vi.mocked(createArchiveBundle).mockImplementation(async () => { active = false; return new Blob(['private paper']) })
    const record = { id: 'archive-1', file_status: 'pending', snapshot: captureSnapshot(paper, TEMPLATES[0], style, 'student', true) } as ArchiveDetail
    await expect(completeArchive(record, undefined, () => active)).rejects.toThrow('保存已停止')
    expect(fetch).not.toHaveBeenCalled()
  })
})
