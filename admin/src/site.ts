/** 后台「小程序管理」—— 运营内容接口封装（分类 / Banner / 公告 / 协议文档 / 字典 / 看板） */

import type { ApiSchemas } from '../../shared/api-schema'
import { request } from './api'

export type AccessLevel = 'inherit' | 'free' | 'vip'

export interface Category {
  id: string; name: string; description: string; icon: string
  sort_order: number; is_visible: boolean; revision: number
  created_at: number; updated_at: number; paper_count: number
}

export type BannerTarget = 'none' | 'keyword' | 'category' | 'subject' | 'paper'
export interface Banner {
  id: string; kicker: string; title: string; subtitle: string; action_label: string
  target_type: BannerTarget; target_value: string
  image_url: string | null; image_mime: string; image_bytes: number; image_fit: 'contain' | 'cover'
  sort_order: number; is_visible: boolean; revision: number; created_at: number; updated_at: number
}

export type NoticeState = 'active' | 'scheduled' | 'expired' | 'hidden'
export interface Notice {
  id: string; title: string; body: string
  placement: 'popup' | 'banner'; level: 'info' | 'warning'
  starts_at: number; ends_at: number; is_visible: boolean; revision: number
  created_at: number; updated_at: number; state: NoticeState
}

export interface SiteDocument { key: 'agreement' | 'privacy'; title: string; body: string; revision: number; updated_at: number }

export type DictionaryKind = 'grade' | 'subject' | 'knowledge_point'
export interface DictionaryItem {
  id: string; kind: DictionaryKind; parent: string; value: string; label: string
  sort_order: number; is_visible: boolean; revision: number; created_at: number; updated_at: number
}

export interface RankedPaper { id: string; title: string; category: string; total: number }
export interface CategoryStat { name: string; papers: number; favorites: number; downloads: number }
export interface Analytics {
  papers: { total: number; draft: number; published: number; withdrawn: number }
  engagement: { favorites: number; downloads: number }
  top_favorites: RankedPaper[]
  top_downloads: RankedPaper[]
  by_category: CategoryStat[]
  users: { total: number; active: number; vip: number; new_7d: number; new_30d: number }
  new_users_timeline: { date: string; total: number }[]
  idle_papers: { id: string; title: string; category: string; published_at: number }[]
  papers_without_category: number
}

const base = '/api/v1/admin/site'
export interface HomeSettings { revision: number; banner_mode: 'welcome' | 'operations' }
export const getHomeSettings = () => request<HomeSettings>(base + '/home-settings')
export const saveHomeSettings = (adminId: number, body: HomeSettings) =>
  request<HomeSettings>(base + '/home-settings', mutation('PUT', adminId, body))

function mutation(method: string, adminId: number, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(adminId) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }
}

/* ── 分类 ── */

export function siteCategories() { return request<{ items: Category[] }>(base + '/categories') }

export function createCategory(adminId: number, body: ApiSchemas["CategoryInput"]) {
  return request<Category>(base + '/categories', mutation('POST', adminId, body))
}

export function updateCategory(adminId: number, id: string, body: ApiSchemas["CategoryUpdate"]) {
  return request<Category>(base + '/categories/' + encodeURIComponent(id), mutation('PUT', adminId, body))
}

export function deleteCategory(adminId: number, id: string, revision: number) {
  return request<void>(base + '/categories/' + encodeURIComponent(id) + '?revision=' + revision, mutation('DELETE', adminId))
}

export function reorderCategories(adminId: number, ids: string[]) {
  return request<{ items: Category[] }>(base + '/categories/order', mutation('PUT', adminId, { ids }))
}

/* ── Banner ── */

export function siteBanners() { return request<{ items: Banner[] }>(base + '/banners') }

export function createBanner(adminId: number, body: ApiSchemas["BannerInput"]) {
  return request<Banner>(base + '/banners', mutation('POST', adminId, body))
}

export function updateBanner(adminId: number, id: string, body: ApiSchemas["BannerUpdate"]) {
  return request<Banner>(base + '/banners/' + encodeURIComponent(id), mutation('PUT', adminId, body))
}

export function deleteBanner(adminId: number, id: string, revision: number) {
  return request<void>(base + '/banners/' + encodeURIComponent(id) + '?revision=' + revision, mutation('DELETE', adminId))
}

/** 图片以原始字节 PUT 上传，服务端按 Content-Type 校验格式与尺寸 */
export function uploadBannerImage(adminId: number, id: string, file: File, revision: number) {
  return request<Banner>(base + '/banners/' + encodeURIComponent(id) + '/image?revision=' + revision, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'image/jpeg', 'X-Workspace-User': String(adminId) },
    body: file,
  })
}

export function clearBannerImage(adminId: number, id: string, revision: number) {
  return request<Banner>(base + '/banners/' + encodeURIComponent(id) + '/image?revision=' + revision, mutation('DELETE', adminId))
}

export function bannerImageUrl(id: string, revision?: number) { return base + '/banners/' + encodeURIComponent(id) + '/image' + (revision ? '?v=' + revision : '') }

/* ── 公告与弹窗 ── */

export function siteNotices() { return request<{ items: Notice[] }>(base + '/notices') }

export function createNotice(adminId: number, body: ApiSchemas["NoticeInput"]) {
  return request<Notice>(base + '/notices', mutation('POST', adminId, body))
}

export function updateNotice(adminId: number, id: string, body: ApiSchemas["NoticeUpdate"]) {
  return request<Notice>(base + '/notices/' + encodeURIComponent(id), mutation('PUT', adminId, body))
}

export function deleteNotice(adminId: number, id: string, revision: number) {
  return request<void>(base + '/notices/' + encodeURIComponent(id) + '?revision=' + revision, mutation('DELETE', adminId))
}

/* ── 协议与隐私页 ── */

export function siteDocuments() { return request<{ items: SiteDocument[] }>(base + '/documents') }

export function updateDocument(adminId: number, key: string, body: ApiSchemas["DocumentUpdate"]) {
  return request<SiteDocument>(base + '/documents/' + encodeURIComponent(key), mutation('PUT', adminId, body))
}

/* ── 年级 / 科目字典 ── */

export function siteDictionary(kind = '', parent = '') {
  const params = new URLSearchParams()
  if (kind) params.set('kind', kind)
  if (parent) params.set('parent', parent)
  const query = params.toString()
  return request<{ items: DictionaryItem[] }>(base + '/dictionary' + (query ? '?' + query : ''))
}

export function dictionaryLinks() {
  return request<{ links: { parent_id: string; child_id: string }[] }>(base + '/dictionary/links')
}

export function setDictionaryLinks(adminId: number, gradeId: string, subjectIds: string[]) {
  return request<{ grade_id: string; subject_ids: string[]; subject_values: string[] }>(
    base + '/dictionary/links/' + encodeURIComponent(gradeId), mutation('PUT', adminId, { subject_ids: subjectIds }))
}

export function unlistedDictionary() {
  return request<{ grade: string[]; subject: string[] }>(base + '/dictionary/unlisted')
}

export function adoptDictionary(adminId: number, kind: 'grade' | 'subject', values: string[]) {
  return request<{ added: number; items: DictionaryItem[] }>(base + '/dictionary/adopt', mutation('POST', adminId, { kind, values }))
}

export function createDictionary(adminId: number, body: ApiSchemas["DictionaryInput"]) {
  return request<DictionaryItem>(base + '/dictionary', mutation('POST', adminId, body))
}

export function updateDictionary(adminId: number, id: string, body: ApiSchemas["DictionaryUpdate"]) {
  return request<DictionaryItem>(base + '/dictionary/' + encodeURIComponent(id), mutation('PUT', adminId, body))
}

export function deleteDictionary(adminId: number, id: string, revision: number) {
  return request<void>(base + '/dictionary/' + encodeURIComponent(id) + '?revision=' + revision, mutation('DELETE', adminId))
}

/* ── 内容数据看板 ── */

export function siteAnalytics() { return request<Analytics>(base + '/analytics') }

/** 整组原子排序，任意版本冲突均不会产生部分更新。 */
export function reorderDictionary(adminId: number, body: ApiSchemas['DictionaryReorder']) {
  return request<{ items: DictionaryItem[] }>(base + '/dictionary/reorder', mutation('POST', adminId, body))
}
