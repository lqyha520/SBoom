import { AUTH_EXPIRED_EVENT, FORBIDDEN_EVENT, ApiError, AuthError, ForbiddenError, adminAccountEpoch, accountChanged, request } from './api'
import type { ApiSchemas } from '../../shared/api-schema'
import { backoff, parseErrorDetail } from '../../shared/http'
import type { DownloadSettings } from './download-settings'

export type PublicationStatus = 'draft' | 'published' | 'withdrawn'
export interface CatalogPaper extends DownloadSettings {
  tags?: import('./growth').CatalogTag[]
  view_access: 'inherit' | 'free' | 'vip'; download_access: 'inherit' | 'free' | 'vip'
  required_view: 'free' | 'vip'; required_download: 'free' | 'vip'; question_types: string[]
  id: string; title: string; description: string; category: string; category_id?: string; status: PublicationStatus
  featured: boolean; revision: number; grade: string; subject: string; version: number
  release_number?: number; update_note?: string; can_view?: boolean; can_download?: boolean
  reviewed_at?: number; answer_readiness?: string
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
export function createPublication(userId: number, body: ApiSchemas["CatalogCreate"]) {
  return request<CatalogDetail>(base + '/papers', mutation('POST', userId, body))
}
export interface CatalogImportMeta extends DownloadSettings {
  title: string; grade: string; subject: string; description: string
  category_id: string; mode: 'student' | 'answersOnly' | 'withAnswers'
  view_access: string; download_access: string
}
export type UploadProgress = (percent: number) => void
/** 上传空闲超时和服务器处理超时分别计时；仅限流且未受理时安全重试。 */
export async function uploadPdf<T>(url: string, userId: number, file: File, progress?: UploadProgress, signal?: AbortSignal): Promise<T> {
  const epoch = adminAccountEpoch()
  for (let attempt = 0; ; attempt++) {
    if (signal?.aborted) throw new DOMException('上传已中断', 'AbortError')
    if (epoch !== adminAccountEpoch()) throw new AuthError('登录账号已变化，请刷新后重试')
    const result = await new Promise<{ data?: T; retryAfter?: number }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      let phaseTimer: ReturnType<typeof setTimeout>
      const overallTimer = setTimeout(() => timeout('上传与处理总耗时过长，请先检查是否已创建草稿'), 600000)
      const cleanup = () => { clearTimeout(phaseTimer); clearTimeout(overallTimer); signal?.removeEventListener('abort', abort) }
      const fail = (cause: Error) => { cleanup(); reject(cause) }
      const timeout = (message: string) => { fail(new ApiError(message, 0, 'timeout')); xhr.abort?.() }
      const arm = (ms: number, message: string) => { clearTimeout(phaseTimer); phaseTimer = setTimeout(() => timeout(message), ms) }
      const abort = () => { fail(new DOMException('上传已中断', 'AbortError')); xhr.abort?.() }
      xhr.open('POST', url)
      xhr.timeout = 0
      xhr.setRequestHeader('Content-Type', 'application/pdf')
      xhr.setRequestHeader('X-Workspace-User', String(userId))
      xhr.upload.onprogress = event => { arm(120000, '上传长时间没有进展，请检查网络'); if (event.lengthComputable) progress?.(Math.round(event.loaded / event.total * 100)) }
      xhr.upload.onload = () => { progress?.(100); arm(240000, '文件处理超时，请先检查是否已创建草稿，再重试') }
      xhr.onerror = () => fail(new ApiError('网络异常，请检查连接；重试前可检查是否已创建草稿'))
      xhr.ontimeout = () => fail(new ApiError('处理超时，请先检查是否已创建草稿，再重试'))
      xhr.onabort = () => fail(new DOMException('上传已中断', 'AbortError'))
      xhr.onload = () => {
        cleanup()
        if (epoch !== adminAccountEpoch()) { reject(new AuthError('登录账号已变化，请刷新后重试')); return }
        let data: unknown
        try { data = JSON.parse(xhr.responseText) } catch { data = null }
        const detail = parseErrorDetail(data, `请求失败（${xhr.status}）`)
        if (xhr.status === 401) { window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail })); reject(new AuthError('请重新登录后重试，导入清单已保留')); return }
        if (xhr.status === 403) { window.dispatchEvent(new CustomEvent(FORBIDDEN_EVENT)); reject(new ForbiddenError('没有管理员权限')); return }
        if (detail.code === 'account_changed') { accountChanged(); reject(new AuthError('登录账号已变化，请刷新后重试')); return }
        if (xhr.status === 429 && attempt < 1) {
          const header = xhr.getResponseHeader?.('Retry-After') || '1'
          const seconds = /^\d+$/.test(header) ? Number(header) : Math.max(0, (Date.parse(header) - Date.now()) / 1000)
          if (Number.isFinite(seconds) && seconds <= 30) { resolve({ retryAfter: Math.max(500, seconds * 1000) }); return }
        }
        if (xhr.status < 200 || xhr.status >= 300) { reject(new ApiError(detail.message, xhr.status, detail.code, detail.requestId)); return }
        if (!data) { reject(new ApiError('服务响应无效，请检查是否已创建草稿')); return }
        resolve({ data: data as T })
      }
      signal?.addEventListener('abort', abort, { once: true })
      arm(120000, '上传长时间没有进展，请检查网络')
      xhr.send(file)
    })
    if (result.retryAfter !== undefined) { await backoff(result.retryAfter); continue }
    return result.data as T
  }
}
/** 手动导入外部 PDF：服务端渲染预览页并直接创建草稿 */
export function importPublication(userId: number, file: File, meta: CatalogImportMeta, progress?: UploadProgress) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(meta)) if (value !== undefined) params.set(key, value)
  return uploadPdf<CatalogDetail>(base + '/import?' + params, userId, file, progress)
}
/** 导入一份外部 PDF 直接挂为该资料的打印版本（默认答案解析版），不单独创建公共条目 */
export function attachImportedEdition(userId: number, catalogId: string, revision: number, kind: 'student' | 'answers', file: File, progress?: UploadProgress, confirmPublication = false) {
  return uploadPdf<{ revision: number; editions: NonNullable<CatalogDetail['editions']> }>(base + '/papers/' + encodeURIComponent(catalogId) + '/editions/import?kind=' + kind + '&revision=' + revision + '&confirm_publication=' + confirmPublication, userId, file, progress)
}
export function updatePublication(userId: number, id: string, body: ApiSchemas["CatalogUpdate"]) {
  return request<CatalogDetail>(base + '/papers/' + encodeURIComponent(id), mutation('PUT', userId, body))
}
export function deletePublication(userId: number, item: CatalogPaper) {
  return request<void>(base + '/papers/' + encodeURIComponent(item.id) + '?revision=' + item.revision, mutation('DELETE', userId))
}
