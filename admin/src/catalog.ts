import { AUTH_EXPIRED_EVENT, AuthError, request } from './api'
import type { DownloadSettings } from './download-settings'

export type PublicationStatus = 'draft' | 'published' | 'withdrawn'
export interface CatalogPaper extends DownloadSettings {
  tags?: import('./growth').CatalogTag[]
  view_access: 'inherit' | 'free' | 'vip'; download_access: 'inherit' | 'free' | 'vip'
  required_view: 'free' | 'vip'; required_download: 'free' | 'vip'; question_types: string[]
  id: string; title: string; description: string; category: string; category_id?: string; status: PublicationStatus
  featured: boolean; revision: number; grade: string; subject: string; version: number
  release_number?: number; update_note?: string; can_view?: boolean; can_download?: boolean
  question_count: number; page_count: number; file_status: string; thumbnail_url: string | null
  updated_at: number; favorite_count?: number; download_users?: number
}
export interface CatalogAsset { id: string; kind: 'pdf' | 'page'; page_number: number; url: string }
export interface CatalogDetail extends CatalogPaper { assets: CatalogAsset[]; editions?: import('./growth').Edition[]; versions?: { release_number: number; note: string; created_at: number }[] }
export interface CatalogStats { total: number; published: number; draft: number; withdrawn: number; favorites: number; downloads: number }
export interface CatalogSource { id: string; title: string; grade: string; subject: string; version: number; file_status: string; question_count: number }
export interface Page<T> { items: T[]; total: number; has_more: boolean }
export interface PublicationEdit extends DownloadSettings {
  view_access: 'inherit' | 'free' | 'vip'; download_access: 'inherit' | 'free' | 'vip'
  revision: number; title: string; description: string; category_id: string; status: PublicationStatus
  featured: boolean; confirm_publication: boolean
}

const base = '/api/v1/admin/catalog'
export function catalogList(q: string, status: string, offset: number) {
  return request<Page<CatalogPaper>>(base + '/papers?' + new URLSearchParams({ q, status, offset: String(offset), limit: '20' }))
}
export function catalogStats() { return request<CatalogStats>(base + '/summary') }
export function catalogDetail(id: string) { return request<CatalogDetail>(base + '/papers/' + encodeURIComponent(id)) }
export function catalogSources(q: string, offset = 0) {
  return request<Page<CatalogSource>>(base + '/sources?' + new URLSearchParams({ q, offset: String(offset), limit: '20' }))
}
function mutation(method: string, userId: number, body?: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(userId) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) }
}
export function createPublication(userId: number, body: DownloadSettings & { paper_id: string; grade?: string; subject?: string; title: string; description: string; category_id: string; view_access: string; download_access: string }) {
  return request<CatalogDetail>(base + '/papers', mutation('POST', userId, body))
}
export interface CatalogImportMeta extends DownloadSettings {
  title: string; grade: string; subject: string; description: string
  category_id: string; mode: 'student' | 'answersOnly' | 'withAnswers'
  view_access: string; download_access: string
}
export type UploadProgress = (percent: number) => void
/** Upload progress measures transferred bytes; PDF processing continues after 100%. */
export function uploadPdf<T>(url: string, userId: number, file: File, progress?: UploadProgress): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.timeout = 120000
    xhr.setRequestHeader('Content-Type', 'application/pdf')
    xhr.setRequestHeader('X-Workspace-User', String(userId))
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress?.(Math.round(event.loaded / event.total * 100)) }
    xhr.upload.onload = () => progress?.(100)
    xhr.onerror = () => reject(new Error('网络异常，请检查连接；重试前可检查是否已创建草稿'))
    xhr.ontimeout = () => reject(new Error('处理超时，请先检查是否已创建草稿，再重试'))
    xhr.onabort = () => reject(new Error('上传已中断'))
    xhr.onload = () => {
      if (xhr.status === 401) {
        window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT)); reject(new AuthError('登录已过期')); return
      }
      if (xhr.status === 403) { reject(new AuthError('没有管理员权限')); return }
      let data: any
      try { data = JSON.parse(xhr.responseText) } catch { reject(new Error('服务响应无效，请检查是否已创建草稿')); return }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = data?.detail
        reject(new Error(typeof detail === 'string' ? detail : detail?.error || `HTTP ${xhr.status}`)); return
      }
      resolve(data as T)
    }
    xhr.send(file)
  })
}
/** 手动导入外部 PDF：服务端渲染预览页并直接创建草稿 */
export function importPublication(userId: number, file: File, meta: CatalogImportMeta, progress?: UploadProgress) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(meta)) if (value !== undefined) params.set(key, value)
  return uploadPdf<CatalogDetail>(base + '/import?' + params, userId, file, progress)
}
/** 导入一份外部 PDF 直接挂为该资料的打印版本（默认答案解析版），不单独创建公共条目 */
export function attachImportedEdition(userId: number, catalogId: string, revision: number, kind: 'student' | 'answers', file: File, progress?: UploadProgress) {
  return uploadPdf<{ revision: number; editions: { kind: string; label: string }[] }>(base + '/papers/' + encodeURIComponent(catalogId) + '/editions/import?kind=' + kind, userId, file, progress)
}
export function updatePublication(userId: number, id: string, body: PublicationEdit) {
  return request<CatalogDetail>(base + '/papers/' + encodeURIComponent(id), mutation('PUT', userId, body))
}
export function deletePublication(userId: number, item: CatalogPaper) {
  return request<void>(base + '/papers/' + encodeURIComponent(item.id) + '?revision=' + item.revision, mutation('DELETE', userId))
}
