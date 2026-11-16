import type { ApiResponse, ApiSchemas } from '../../shared/api-schema'
import { captureWorkspaceGuard, request } from './api'
import type { PaperData, PaperStyle, PaperTemplate } from './types'
import { randomId, sha256Hex } from '../../shared/webcrypto'

export interface ArchiveSnapshot {
  schema_version: 1 | 2
  paper: PaperData
  additional_papers?: PaperData[]
  collection_title?: string
  template: PaperTemplate
  style: PaperStyle
  export_options: { mode: 'student' | 'withAnswers' | 'answersOnly'; addDay: boolean; renderer_version: 'web-v1' | 'web-v2'; separate_answers?: boolean }
}
type ArchiveWire = ApiResponse<'GET /api/v1/library/papers/{paper_id}'>
export type ArchiveAsset = Pick<ApiSchemas['ArchiveAssetResponse'], 'id' | 'kind' | 'page_number' | 'byte_size' | 'url'> & { edition?: 'answers'; label?: string }
export type ArchiveSummary = Pick<ArchiveWire, 'id' | 'title' | 'grade' | 'subject' | 'version' | 'question_count' | 'folder_id' | 'folder_name' | 'group_name' | 'favorite' | 'file_status' | 'file_error' | 'page_count' | 'created_at' | 'thumbnail_url'> & Partial<Pick<ArchiveWire, 'publication_id'>>
export interface ArchiveDetail extends ArchiveSummary { snapshot: ArchiveSnapshot; assets: ArchiveAsset[] }
export interface ArchiveFolder { id: string; name: string; paper_count: number }
export interface ArchiveRequest { request_id: string; source_id: string; snapshot: ArchiveSnapshot; folder_id: string | null; group_id: string; group_name: string }

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}
export function captureSnapshot(paper: PaperData, template: PaperTemplate, style: PaperStyle, mode: ArchiveSnapshot['export_options']['mode'], addDay: boolean, separateAnswers = false): ArchiveSnapshot {
  return JSON.parse(JSON.stringify({ schema_version: 1, paper, template, style,
    export_options: { mode, addDay, renderer_version: 'web-v1', ...(separateAnswers && mode === 'withAnswers' ? { separate_answers: true } : {}) } }))
}
export function archivePapers(snapshot: ArchiveSnapshot): PaperData[] {
  return [snapshot.paper, ...(snapshot.additional_papers || [])]
}
export async function captureCollection(papers: PaperData[], template: PaperTemplate, style: PaperStyle,
  mode: ArchiveSnapshot['export_options']['mode'], addDay: boolean, title: string, separateAnswers = false) {
  if (papers.length < 2 || papers.length > 100) throw new Error('每次可合并 2 至 100 份试卷，请调整保存范围')
  if (papers.some(paper => paper.grade !== papers[0].grade || paper.subject !== papers[0].subject)) throw new Error('请将相同年级、科目的试卷合并保存')
  papers.forEach(paper => { paper.archiveSourceId ||= randomId() })
  // 以有序的原卷标识识别合集；重开弹窗、重试或切换答案模式仍属于同一版本序列。
  const identity = JSON.stringify(papers.map(paper => paper.archiveSourceId))
  const snapshot: ArchiveSnapshot = JSON.parse(JSON.stringify({
    ...captureSnapshot(papers[0], template, style, mode, addDay), schema_version: 2,
    additional_papers: papers.slice(1),
    collection_title: title.trim() || papers[0].title || papers[0].grade + papers[0].subject + '试卷',
    // 标记新的渲染行为，重新保存时不能复用旧版添加过标题编号的 PDF。
    export_options: { ...captureSnapshot(papers[0], template, style, mode, addDay, separateAnswers).export_options, renderer_version: 'web-v2' },
  }))
  return { source_id: 'merged-' + await sha256Hex(new TextEncoder().encode(identity)), snapshot }
}
export function fetchArchiveFolders() { return request<{ items: ArchiveFolder[] }>('/api/v1/library/folders') }
export function createArchiveFolder(name: string) { return request<{ id: string; name: string }>('/api/v1/library/folders', json('POST', { name })) }
export function fetchArchives(q = '', folder = '', offset = 0) {
  const query = new URLSearchParams({ q, offset: String(offset), limit: '20' })
  if (folder) query.set('folder_id', folder)
  return request<Omit<ApiResponse<'GET /api/v1/library/papers'>, 'items'> & { items: ArchiveSummary[] }>('/api/v1/library/papers?' + query)
}
export function fetchArchive(id: string) { return request<ArchiveDetail>('/api/v1/library/papers/' + encodeURIComponent(id)) }
export function createArchive(body: ArchiveRequest) { return request<ArchiveDetail>('/api/v1/library/papers', json('POST', body)) }
export function patchArchive(id: string, body: { title?: string; folder_id?: string | null; favorite?: boolean }) {
  return request<ArchiveDetail>('/api/v1/library/papers/' + encodeURIComponent(id), json('PUT', body))
}
export function deleteArchive(id: string) { return request<void>('/api/v1/library/papers/' + encodeURIComponent(id), { method: 'DELETE' }) }
export type ArchiveDeletePreview = ApiResponse<'POST /api/v1/library/papers/batch-delete/preview'>
export type ArchiveDeleteResult = ApiResponse<'POST /api/v1/library/papers/batch-delete'>
export function previewArchiveDeletion(ids: string[]) {
  return request<ArchiveDeletePreview>('/api/v1/library/papers/batch-delete/preview', json('POST', { ids }))
}
export function deleteArchives(ids: string[]) {
  return request<ArchiveDeleteResult>('/api/v1/library/papers/batch-delete', json('POST', { ids, confirmed: true }))
}
export function fetchLibraryCapacity() {
  return request<{ storage_bytes: number; storage_limit_bytes: number }>('/api/v1/library/summary')
}
export async function completeArchive(record: ArchiveDetail, progress?: (message: string) => void, isActive = () => true, signal?: AbortSignal) {
  const assertOwner = captureWorkspaceGuard()
  function assertActive() {
    assertOwner()
    if (!isActive() || signal?.aborted) throw new Error('保存已停止，可在云端试卷中重试未完成的文件')
  }
  assertActive()
  if (record.file_status === 'ready') return record
  if (!record.snapshot?.paper?.sections?.length) throw new Error('请回到图片出题或原上传入口重试保存，云端会复用这份归档')
  const { createArchiveBundle } = await import('./exporter')
  assertActive()
  progress?.('正在生成 PDF 与预览图')
  const bundle = await createArchiveBundle(record.snapshot, progress, { signal, isActive })
  assertActive()
  progress?.('正在上传文件')
  return request<ArchiveDetail>(`/api/v1/library/papers/${encodeURIComponent(record.id)}/files`,
    { method: 'PUT', headers: { 'Content-Type': 'application/zip' }, body: bundle, signal }, 120000)
}

export function safeLibraryUrl(value: string): string {
  const url = new URL(value, location.origin)
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/library/') || url.username || url.password) throw new Error('下载地址无效，请刷新试卷库后重试')
  return url.href
}
