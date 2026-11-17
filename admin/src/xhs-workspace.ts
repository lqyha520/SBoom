import type { ApiResponse, ApiSchemas } from '../../shared/api-schema'
import { request } from './api'
import type { DraftData, IdeaData, PublicationData, WorkflowRecord } from './xhs-workflow'

const base = '/api/v1/admin/xhs-workspace'
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export type AssetMetadata = Required<ApiSchemas['AssetMetadata']>
export type CoverTemplate = Pick<DraftData, 'theme' | 'cover_title' | 'cover_subtitle' | 'cards'>
export type Asset = Omit<ApiResponse<'GET /api/v1/admin/xhs-workspace/assets/{identifier}'>, 'data' | 'template' | 'created_at' | 'updated_at'> & { data: AssetMetadata; template: CoverTemplate | null }
export const assetDefaults = (): AssetMetadata => ({ title: '', tags: [], rights: 'unknown', source: '', notes: '', archived: false })
export const assetRights = { unknown: '待核实来源', original: '本人原创', licensed: '已获授权' }
export const listAssets = (q = '', kind = '', archived = false, page = 1) => request<{ items: Asset[]; total: number; used_bytes: number; quota_bytes: number }>(`${base}/assets?${new URLSearchParams({ q, kind, archived: String(archived), page: String(page) })}`)
export const uploadAsset = (file: File) => request<Asset>(`${base}/assets/file?title=${encodeURIComponent(file.name.slice(0, 120))}`, { method: 'POST', headers: { 'Content-Type': file.type }, body: file }, 'json', 120_000)
export const saveAsset = (asset: Asset, data: AssetMetadata) => request<Asset>(`${base}/assets/${asset.id}`, json('PUT', { revision: asset.revision, data }))
export const deleteAsset = (asset: Asset) => request<void>(`${base}/assets/${asset.id}?revision=${asset.revision}`, { method: 'DELETE' })
export const assetBlob = (asset: Asset) => request<Blob>(`${base}/assets/${asset.id}/file`, undefined, 'blob', 120_000)
export const assetPreview = (asset: Asset) => request<Blob>(`${base}/assets/${asset.id}/preview`, undefined, 'blob', 120_000)
export const assetThumbnail = (asset: Asset) => request<Blob>(`${base}/assets/${asset.id}/thumbnail`, undefined, 'blob')
export const getAsset = (id: string) => request<Asset>(`${base}/assets/${id}`)
export const saveCoverTemplate = (data: AssetMetadata, template: CoverTemplate) => request<Asset>(`${base}/assets/template`, json('POST', { data, template }))
export interface CalendarItem extends WorkflowRecord<PublicationData> { account_key: string; calendar_at: string | null; conflicts: string[]; conflict_count?: number }
export interface CalendarData { items: CalendarItem[]; unscheduled: CalendarItem[]; accounts: { id: string; name: string; last_published_at: string | null }[]; unscheduled_total?: number; unscheduled_page?: number; page_size?: number }
export const getPublicationCalendar = (start: string, end: string, account = '', unscheduled_page = 1) => request<CalendarData>(`${base}/calendar?${new URLSearchParams({ start, end, account, unscheduled_page: String(unscheduled_page) })}`)
export const previewReviewIdea = (id: string, checkpoint: number) => request<{ data: IdeaData; reasons: string[]; series: string }>(`${base}/analytics/${id}/idea-preview?checkpoint=${checkpoint}`)
export const getTutorial = (create = false) => request<{ records: Partial<Record<'ideas' | 'materials' | 'drafts' | 'publications', string>> }>(`${base}/tutorial`, create ? json('POST', {}) : undefined)
export type TaskCategory = 'review' | 'publish' | 'analytics'
export interface TodayTask extends WorkflowRecord { checkpoint?: 1 | 3 | 7; due_at?: string }
export const getTodayTasks = (category: TaskCategory, page: number) => {
  const start = new Date(); start.setHours(0, 0, 0, 0)
  const end = new Date(start); end.setDate(end.getDate() + 1)
  return request<{ items: TodayTask[]; total: number; page: number }>(`${base}/today?${new URLSearchParams({ start: start.toISOString(), end: end.toISOString(), category, page: String(page) })}`)
}
export function localDay(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
export function weekStart(date = new Date()) { const result = new Date(date); result.setHours(0, 0, 0, 0); result.setDate(result.getDate() - (result.getDay() + 6) % 7); return result }
export const assetFileName = (asset: Asset) => asset.data.title.replace(/[\\/:*?"<>|]/g, '_') + (asset.data.title.match(/\.(png|jpe?g|webp|mp4)$/i) ? '' : ({ 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'video/mp4': '.mp4' }[asset.media_type] || ''))
