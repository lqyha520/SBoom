import { captureWorkspaceGuard, request } from './api'
import type { PaperData, PaperStyle, PaperTemplate } from './types'

export interface ArchiveSnapshot {
  schema_version: 1
  paper: PaperData
  template: PaperTemplate
  style: PaperStyle
  export_options: { mode: 'student' | 'withAnswers' | 'answersOnly'; addDay: boolean; renderer_version: 'web-v1' }
}
export interface ArchiveAsset { id: string; kind: 'pdf' | 'page'; page_number: number; byte_size: number; url: string }
export interface ArchiveSummary {
  id: string; title: string; grade: string; subject: string; version: number; question_count: number
  folder_id: string | null; folder_name: string | null; group_name: string; favorite: boolean
  file_status: 'pending' | 'uploading' | 'failed' | 'ready'; file_error: string; page_count: number
  created_at: number; thumbnail_url: string | null
}
export interface ArchiveDetail extends ArchiveSummary { snapshot: ArchiveSnapshot; assets: ArchiveAsset[] }
export interface ArchiveFolder { id: string; name: string; paper_count: number }
export interface ArchiveRequest { request_id: string; source_id: string; snapshot: ArchiveSnapshot; folder_id: string | null; group_id: string; group_name: string }

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}
export function captureSnapshot(paper: PaperData, template: PaperTemplate, style: PaperStyle, mode: ArchiveSnapshot['export_options']['mode'], addDay: boolean): ArchiveSnapshot {
  return JSON.parse(JSON.stringify({ schema_version: 1, paper, template, style, export_options: { mode, addDay, renderer_version: 'web-v1' } }))
}
export function fetchArchiveFolders() { return request<{ items: ArchiveFolder[] }>('/api/v1/library/folders') }
export function createArchiveFolder(name: string) { return request<{ id: string; name: string }>('/api/v1/library/folders', json('POST', { name })) }
export function fetchArchives(q = '', folder = '', offset = 0) {
  const query = new URLSearchParams({ q, offset: String(offset), limit: '20' })
  if (folder) query.set('folder_id', folder)
  return request<{ items: ArchiveSummary[]; total: number; has_more: boolean }>('/api/v1/library/papers?' + query)
}
export function fetchArchive(id: string) { return request<ArchiveDetail>('/api/v1/library/papers/' + encodeURIComponent(id)) }
export function createArchive(body: ArchiveRequest) { return request<ArchiveDetail>('/api/v1/library/papers', json('POST', body)) }
export function patchArchive(id: string, body: { title?: string; folder_id?: string | null; favorite?: boolean }) {
  return request<ArchiveDetail>('/api/v1/library/papers/' + encodeURIComponent(id), json('PUT', body))
}
export function deleteArchive(id: string) { return request<void>('/api/v1/library/papers/' + encodeURIComponent(id), { method: 'DELETE' }) }
export async function completeArchive(record: ArchiveDetail, progress?: (message: string) => void, isActive = () => true, signal?: AbortSignal) {
  const assertOwner = captureWorkspaceGuard()
  function assertActive() {
    assertOwner()
    if (!isActive() || signal?.aborted) throw new Error('保存已停止，可在云端试卷中重试未完成的文件')
  }
  assertActive()
  if (record.file_status === 'ready') return record
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
