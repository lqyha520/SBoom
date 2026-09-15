import { request } from './api'

export type PublicationStatus = 'draft' | 'published' | 'withdrawn'
export interface CatalogPaper {
  view_access: 'inherit' | 'free' | 'vip'; download_access: 'inherit' | 'free' | 'vip'
  required_view: 'free' | 'vip'; required_download: 'free' | 'vip'; question_types: string[]
  id: string; title: string; description: string; category: string; category_id?: string; status: PublicationStatus
  featured: boolean; revision: number; grade: string; subject: string; version: number
  question_count: number; page_count: number; file_status: string; thumbnail_url: string | null
  updated_at: number; favorite_count?: number; download_users?: number
}
export interface CatalogAsset { id: string; kind: 'pdf' | 'page'; page_number: number; url: string }
export interface CatalogDetail extends CatalogPaper { assets: CatalogAsset[] }
export interface CatalogStats { total: number; published: number; draft: number; withdrawn: number; favorites: number; downloads: number }
export interface CatalogSource { id: string; title: string; grade: string; subject: string; version: number; file_status: string; question_count: number }
export interface Page<T> { items: T[]; total: number; has_more: boolean }
export interface PublicationEdit {
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
export function createPublication(userId: number, body: { paper_id: string; title: string; description: string; category_id: string; view_access: string; download_access: string }) {
  return request<CatalogDetail>(base + '/papers', mutation('POST', userId, body))
}
export function updatePublication(userId: number, id: string, body: PublicationEdit) {
  return request<CatalogDetail>(base + '/papers/' + encodeURIComponent(id), mutation('PUT', userId, body))
}
export function deletePublication(userId: number, item: CatalogPaper) {
  return request<void>(base + '/papers/' + encodeURIComponent(item.id) + '?revision=' + item.revision, mutation('DELETE', userId))
}
