import { request } from './api'
import type { CatalogDetail, CatalogPaper, Page } from './catalog'
import type { MiniUser } from './mini'

export interface SupportSettings { revision: number; wechat: string; phone: string; email: string; hours: string; benefits: string; qr_url?: string }
export interface Feedback {
  id: string; catalog_id: string | null; paper_title: string; username: string; nickname: string
  kind: 'correction' | 'download' | 'membership' | 'other'; body: string
  status: 'pending' | 'processing' | 'resolved' | 'closed'; reply: string; internal_note: string; revision: number; updated_at: number
}
export const statusOptions = [{ value: 'pending', label: '待处理' }, { value: 'processing', label: '处理中' }, { value: 'resolved', label: '已解决' }, { value: 'closed', label: '已关闭' }]
export const kindLabels = { correction: '资料纠错', download: '下载问题', membership: '会员咨询', other: '其他问题' }
export interface MemberEvent { id: string; admin_name: string | null; created_at: number; before: Record<string, unknown>; after: Record<string, unknown> }
export interface Topic {
  id: string; title: string; description: string; is_visible: boolean; sort_order: number; revision: number
  paper_ids: string[]; paper_count: number; papers: { catalog_id: string; title: string; status: string; file_status: string }[]
}
export interface TopicEdit { title: string; description: string; is_visible: boolean; sort_order: number; revision: number; paper_ids: string[] }
export interface UsageAnalytics {
  daily_active: number; weekly_active: number; monthly_active: number
  timeline: { date: string; active_users: number; download_ok: number; download_failed: number; search_miss: number }[]
  search_misses: { query: string; total: number }[]
  download_failures: { catalog_id: string | null; title: string | null; total: number }[]
}
function change<T>(path: string, adminId: number, body: unknown, method = 'POST') {
  return request<T>(path, { method, headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(adminId) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
}
const base = '/api/v1/admin/experience'
export const getSupport = () => request<SupportSettings>(base + '/support')
export const saveSupport = (id: number, body: SupportSettings) => change<SupportSettings>(base + '/support', id, body, 'PUT')
export const getFeedback = (status = '', offset = 0) => request<Page<Feedback>>(base + '/feedback?' + new URLSearchParams({ status, offset: String(offset) }))
export const saveFeedback = (id: number, item: Feedback) => change<Feedback>(base + '/feedback/' + encodeURIComponent(item.id), id, { revision: item.revision, status: item.status, reply: item.reply, internal_note: item.internal_note }, 'PUT')
export const getTopics = () => request<{ items: Topic[] }>(base + '/topics')
export const saveTopic = (id: number, body: TopicEdit, topicId = '') => change<Topic>(base + '/topics' + (topicId ? '/' + encodeURIComponent(topicId) : ''), id, body, topicId ? 'PUT' : 'POST')
export const removeTopic = (id: number, topic: Topic) => change<void>(base + '/topics/' + encodeURIComponent(topic.id) + '?revision=' + topic.revision, id, undefined, 'DELETE')
export const getUsage = () => request<UsageAnalytics>(base + '/analytics')
export const renewMember = (id: number, target: MiniUser, days: number, note: string) => change<MiniUser>('/api/v1/admin/mini-users/' + target.id + '/renew', id, { revision: target.revision, days, note })
export const memberEvents = (id: string, offset = 0) => request<Page<MemberEvent>>('/api/v1/admin/mini-users/' + encodeURIComponent(id) + '/events?offset=' + offset)
export function batchCatalog(id: number, items: CatalogPaper[], body: { action: string; category_id: string; view_access: string; download_access: string; confirm_publication: boolean; tag_ids?: string[] }) {
  return change<{ updated: number }>('/api/v1/admin/catalog/batch', id, { ...body, items: items.map(item => ({ id: item.id, revision: item.revision })) })
}
export const previewCatalog = (id: string, membership: string) => request<CatalogDetail>('/api/v1/admin/catalog/papers/' + encodeURIComponent(id) + '/preview?membership=' + membership)
export const reviseCatalog = (id: number, target: CatalogPaper, paper_id: string, note: string, confirm_publication: boolean) => change<CatalogDetail>('/api/v1/admin/catalog/papers/' + target.id + '/revision', id, { revision: target.revision, paper_id, note, confirm_publication })
