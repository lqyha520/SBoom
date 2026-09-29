import { navigatePage } from './page-navigation'
import { request, type ReadOptions } from './api'

export interface SupportSettings { revision: number; wechat: string; phone: string; email: string; hours: string; benefits: string; qr_url?: string }
export interface Topic { id: string; title: string; description: string; paper_count: number }
export interface FavoriteGroup { id: string; name: string; revision: number; paper_count: number }
export type FeedbackKind = 'correction' | 'download' | 'membership' | 'other'
export interface Feedback {
  id: string; catalog_id: string | null; paper_title: string; kind: FeedbackKind; body: string
  status: 'pending' | 'processing' | 'resolved' | 'closed'; reply: string; created_at: number; updated_at: number
}
export const feedbackKinds: { value: FeedbackKind; label: string }[] = [
  { value: 'correction', label: '资料纠错' }, { value: 'download', label: '下载问题' },
  { value: 'membership', label: '会员开通或续期' }, { value: 'other', label: '其他问题' },
]
export const feedbackStatus = { pending: '待处理', processing: '处理中', resolved: '已解决', closed: '已关闭' }
export const fetchSupport = (options: ReadOptions = {}) => request<SupportSettings>('/api/v1/site/support', 'GET', undefined, options)
export const fetchTopics = (options: ReadOptions = {}) => request<{ items: Topic[] }>('/api/v1/site/topics', 'GET', undefined, options)
export const fetchFeedback = (offset = 0, options: ReadOptions = {}) => request<{ items: Feedback[]; total: number; has_more: boolean }>('/api/v1/mini/feedback?offset=' + offset, 'GET', undefined, options)
export const fetchFeedbackItem = (id: string, options: ReadOptions = {}) => request<Feedback>('/api/v1/mini/feedback/' + encodeURIComponent(id), 'GET', undefined, options)
export const submitFeedback = (body: { kind: FeedbackKind; body: string; catalog_id?: string }) => request<Feedback>('/api/v1/mini/feedback', 'POST', body)
export const fetchGroups = (options: ReadOptions = {}) => request<{ items: FavoriteGroup[] }>('/api/v1/mini/favorite-groups', 'GET', undefined, options)
export const createGroup = (name: string) => request<FavoriteGroup>('/api/v1/mini/favorite-groups', 'POST', { name })
export const renameGroup = (group: FavoriteGroup, name: string) => request<FavoriteGroup>('/api/v1/mini/favorite-groups/' + encodeURIComponent(group.id), 'PUT', { name, revision: group.revision })
export const deleteGroup = (group: FavoriteGroup) => request<void>('/api/v1/mini/favorite-groups/' + encodeURIComponent(group.id) + '?revision=' + group.revision, 'DELETE')
export const assignGroup = (paper: string, group: string | null) => request<void>('/api/v1/mini/favorite-groups/papers/' + encodeURIComponent(paper), 'PUT', { group_id: group })
export const recordView = (id: string) => request<void>('/api/v1/mini/history/' + encodeURIComponent(id), 'POST')
export const clearHistory = () => request<void>('/api/v1/mini/history', 'DELETE')
export function recordEvent(kind: 'active' | 'download_ok' | 'download_failed', catalog_id?: string) {
  return request<void>('/api/v1/mini/events', 'POST', { kind, catalog_id,
    event_id: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 14) })
}
export function openSupport(kind: FeedbackKind = 'other', catalogId = '') {
  navigatePage({ url: '/subpages/support/index?kind=' + kind + (catalogId ? '&paper=' + encodeURIComponent(catalogId) : '') })
}
