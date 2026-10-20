import { request } from './api'
import { downloadBlob } from '../../shared/download'
import type { Page } from './catalog'
export type TagKind = 'textbook' | 'term' | 'unit' | 'knowledge'
export const tagKinds: { value: TagKind; label: string }[] = [{ value: 'textbook', label: '教材' }, { value: 'term', label: '学期' }, { value: 'unit', label: '单元' }, { value: 'knowledge', label: '知识点' }]
export interface CatalogTag { id: string; kind: TagKind; name: string; revision: number; is_visible: boolean; sort_order: number; paper_count: number }
export interface Edition { kind: 'original' | 'student' | 'answers'; paper_id: string; label: string; byte_size: number; mode: string; url?: string }
export interface EditionSource { id: string; title: string; version: number; mode: string; owned_by?: string }
export interface ResourceRequest { id: string; username: string; nickname: string; title: string; grade: string; subject: string; details: string; status: 'pending' | 'planned' | 'fulfilled' | 'closed'; reply: string; catalog_id: string | null; paper_title: string | null; revision: number; created_at: number; updated_at: number }
export interface Demand { fingerprint: string; title: string; grade: string; subject: string; requests: number; users: number }
export const requestStatuses = { pending: '待处理', planned: '已安排', fulfilled: '资料已补齐', closed: '已关闭' }
export interface Closure { id: string; account_name: string; user_id: string | null; reason: string; status: 'pending' | 'cancelled' | 'rejected' | 'completed'; reply: string; revision: number; created_at: number; updated_at: number }
export const closureStatuses = { pending: '等待审核', cancelled: '已撤回', rejected: '审核未通过', completed: '已注销' }
export interface Plan { id: string; name: string; description: string; days: number; price_fen: number; is_active: boolean; sort_order: number; revision: number }
export interface MembershipCard { id: string; code_hint: string; days: number; status: string; redeemed_by: string | null; redeemed_at: number | null; created_at: number; expires_at: number | null }
export type PlanInput = Omit<Plan, 'id'>
export interface PaymentConfig { enabled: boolean; ready: boolean; missing: string[]; ios_enabled: boolean; payment_callback: string; refund_callback: string }
export interface Refund { id: string; reason: string; reply: string; status: 'requested' | 'processing' | 'success' | 'closed' | 'abnormal' | 'rejected'; revision: number; created_at: number; updated_at: number; completed_at: number | null }
export interface Order { id: string; user_id: string | null; username: string; nickname: string; plan_name: string; plan_days: number; amount_fen: number; status: 'created' | 'pending' | 'paid' | 'closed' | 'refunded'; revision: number; created_at: number; paid_at: number | null; expires_at: number; transaction_id: string | null; refund: Refund | null }
export { orderFilterLabels as orderStatuses, adminRefundLabels as refundStatuses } from '../../shared/commerce'
export interface OrderFilter { status?: string; q?: string; start_date?: string; end_date?: string }
export interface Reconciliation { id: string; bill_date: string; status: 'running' | 'complete' | 'error'; error: string; created_at: number; summary: { wechat_paid_fen?: number; wechat_refunded_fen?: number; local_paid_fen?: number; local_refunded_fen?: number; differences?: number; wechat_orders?: number; local_orders?: number }; differences?: { order_id: string; refund_id: string; reason: string; remote_fen: number | null; local_fen: number | null }[] }
export const yuan = (fen: number) => '¥' + (fen / 100).toFixed(2)
export const dateTime = (stamp: number | null) => stamp ? new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'
export const choices = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }))
export function change<T>(path: string, adminId: number, body?: unknown, method = 'POST') { return request<T>(path, { method, headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(adminId) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }) }
const catalog = '/api/v1/admin/catalog', base = '/api/v1/admin/engagement', commerce = '/api/v1/admin/commerce'
export const getTags = () => request<{ items: CatalogTag[] }>(catalog + '/tags')
export const saveTag = (admin: number, tag: Omit<CatalogTag, 'id' | 'paper_count'>, id = '') => change<CatalogTag>(catalog + '/tags' + (id ? '/' + encodeURIComponent(id) : ''), admin, tag, id ? 'PUT' : 'POST')
export const removeTag = (admin: number, item: CatalogTag) => change<void>(catalog + '/tags/' + item.id + '?revision=' + item.revision, admin, undefined, 'DELETE')
export const assignTags = (admin: number, id: string, revision: number, tag_ids: string[]) => change<{ revision: number; tags: CatalogTag[] }>(catalog + '/papers/' + encodeURIComponent(id) + '/labels', admin, { revision, tag_ids }, 'PUT')
export const editionSources = (id: string, q = '') => request<{ items: EditionSource[]; loose?: boolean }>(catalog + '/papers/' + encodeURIComponent(id) + '/edition-sources?q=' + encodeURIComponent(q))
export const saveEdition = (admin: number, id: string, body: { revision: number; kind: 'student' | 'answers'; paper_id: string | null; confirm_publication: boolean }) => change<{ revision: number; editions: Edition[] }>(catalog + '/papers/' + encodeURIComponent(id) + '/editions', admin, body, 'PUT')
export const getRequests = (status = '', fingerprint = '', offset = 0) => request<Page<ResourceRequest> & { demand: Demand[] }>(base + '/requests?' + new URLSearchParams({ status, fingerprint, offset: String(offset) }))
export const resolveRequest = (admin: number, item: ResourceRequest) => change<ResourceRequest>(base + '/requests/' + item.id, admin, { revision: item.revision, status: item.status, reply: item.reply, catalog_id: item.catalog_id }, 'PUT')
export const getClosures = (status = '', offset = 0) => request<Page<Closure>>(base + '/closures?' + new URLSearchParams({ status, offset: String(offset) }))
export const reviewClosure = (admin: number, item: Closure, action: 'approve' | 'reject', reply: string, confirm_deletion: boolean) => change<Closure>(base + '/closures/' + item.id, admin, { revision: item.revision, action, reply, confirm_deletion }, 'PUT')
export const getDelivery = () => request<{ available: boolean; template_id: string; delivery_counts: Record<string, number> }>(base + '/delivery-status')
export const getPlans = () => request<{ items: Plan[]; checkout_enabled: boolean; configuration: PaymentConfig }>(commerce + '/plans')
export const savePlan = (admin: number, plan: PlanInput, id = '') => change<Plan>(commerce + '/plans' + (id ? '/' + encodeURIComponent(id) : ''), admin, plan, id ? 'PUT' : 'POST')
export const getCards = (status = '', offset = 0, q = '') => request<{ items: MembershipCard[]; total: number; has_more: boolean }>(commerce + '/cards?' + new URLSearchParams({ status, offset: String(offset), q }))
export const createCards = (admin: number, days: number, quantity: number, expires_at: number | null) => change<{ items: { code: string; days: number; expires_at: number | null }[] }>(commerce + '/cards', admin, { days, quantity, expires_at })
export const disableCard = (admin: number, id: string) => change<{ status: string }>(commerce + '/cards/' + encodeURIComponent(id) + '/disable', admin)
export const getOrders = (filter: OrderFilter = {}, offset = 0) => request<Page<Order> & { summary: { orders: number; paid_fen: number; refunded_fen: number } }>(commerce + '/orders?' + new URLSearchParams({ ...filter, offset: String(offset) }))
export const syncOrder = (admin: number, id: string) => change<Order>(commerce + '/orders/' + encodeURIComponent(id) + '/sync', admin)
export const getOrder = (id: string) => request<Order>(commerce + '/orders/' + encodeURIComponent(id))
export const cancelOrder = (admin: number, id: string) => change<Order>(commerce + '/orders/' + encodeURIComponent(id) + '/cancel', admin)
export const reviewRefund = (admin: number, refund: Refund, action: 'approve' | 'reject', reply: string, confirm_refund: boolean) => change<Order>(commerce + '/refunds/' + refund.id, admin, { revision: refund.revision, action, reply, confirm_refund }, 'PUT')
export const syncRefund = (admin: number, id: string) => change<Order>(commerce + '/refunds/' + encodeURIComponent(id) + '/sync', admin)
export async function exportOrders(admin: number, filter: OrderFilter) {
  const blob = await request<Blob>(commerce + '/orders/export?' + new URLSearchParams({ ...filter }), { headers: { 'X-Workspace-User': String(admin) } }, 'blob')
  downloadBlob(blob, 'membership-orders.csv', 2000)
}
export const getReconciliations = (offset = 0) => request<Page<Reconciliation>>(commerce + '/reconciliations?offset=' + offset)
export const getReconciliation = (id: string) => request<Reconciliation>(commerce + '/reconciliations/' + encodeURIComponent(id))
export const reconcile = (admin: number, bill_date: string) => change<Reconciliation>(commerce + '/reconciliations', admin, { bill_date })
