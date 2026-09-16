import { reactive } from 'vue'
import { authGeneration, queryString, request } from './api'
import { safeDestination } from './return-route'

export interface Page<T> { items: T[]; total: number; has_more: boolean }
export type TagKind = 'textbook' | 'term' | 'unit' | 'knowledge'
export interface CatalogTag { id: string; kind: TagKind; name: string; paper_count?: number }
export const tagKinds: { kind: TagKind; label: string }[] = [{ kind: 'textbook', label: '教材' }, { kind: 'term', label: '学期' }, { kind: 'unit', label: '单元' }, { kind: 'knowledge', label: '知识点' }]
export type TagFilters = Record<TagKind, string>
export const emptyTags = (): TagFilters => ({ textbook: '', term: '', unit: '', knowledge: '' })
export const fetchTags = () => request<{ items: CatalogTag[] }>('/api/v1/site/catalog-tags')
export interface Message { id: string; kind: string; title: string; body: string; target_type: string; target_id: string; read_at: number | null; created_at: number }
export const inboxState = reactive({ unread: 0 })
export const fetchMessages = (unread = false, offset = 0, limit = 20) => request<Page<Message> & { unread: number }>('/api/v1/mini/messages?' + queryString({ unread, offset, limit }))
export async function refreshUnread() {
  const epoch = authGeneration()
  const result = await fetchMessages(false, 0, 1)
  if (epoch === authGeneration()) inboxState.unread = result.unread
}
export async function readMessages(id = '') {
  const result = await request<{ unread: number }>('/api/v1/mini/messages/' + (id ? encodeURIComponent(id) + '/read' : 'read-all'), 'POST')
  inboxState.unread = result.unread
}
export function messageDestination(message: Pick<Message, 'target_type' | 'target_id'>) {
  const pages: Record<string, string> = { paper: 'paper', feedback: 'support', membership: 'membership', request: 'requests', closure: 'closure', order: 'orders' }
  const page = pages[message.target_type]
  return safeDestination(page ? '/pages/' + page + '/index' + (message.target_id ? '?id=' + encodeURIComponent(message.target_id) : '') : '/pages/messages/index')
}
export const subscriptionConfig = () => request<{ available: boolean; template_id: string }>('/api/v1/mini/message-subscription')
export const grantSubscription = (template_id: string, request_id: string) => request('/api/v1/mini/message-subscription', 'POST', { template_id, request_id })
export function requestKey() { return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 14) }
export interface ResourceRequest { id: string; title: string; grade: string; subject: string; details: string; status: 'pending' | 'planned' | 'fulfilled' | 'closed'; reply: string; catalog_id: string | null; paper_title?: string | null; revision: number; created_at: number; updated_at: number }
export const requestStatus = { pending: '待处理', planned: '已安排', fulfilled: '资料已补齐', closed: '已关闭' }
export const fetchRequests = (offset = 0) => request<Page<ResourceRequest>>('/api/v1/mini/requests?offset=' + offset)
export const fetchResourceRequest = (id: string) => request<ResourceRequest>('/api/v1/mini/requests/' + encodeURIComponent(id))
export const submitRequest = (body: { title: string; grade: string; subject: string; details: string }) => request<ResourceRequest>('/api/v1/mini/requests', 'POST', body)
export interface Closure { id: string; reason: string; status: 'pending' | 'cancelled' | 'rejected' | 'completed'; reply: string; revision: number; updated_at: number }
export const closureStatus = { pending: '等待审核', cancelled: '已撤回', rejected: '审核未通过', completed: '已注销' }
export const fetchClosure = () => request<{ request: Closure | null }>('/api/v1/mini/closure')
export const applyClosure = (reason: string) => request<{ request: Closure }>('/api/v1/mini/closure', 'POST', { reason, acknowledge: true })
export const cancelClosure = (revision: number) => request<{ request: Closure }>('/api/v1/mini/closure?revision=' + revision, 'DELETE')
export interface Plan { id: string; name: string; description: string; days: number; price_fen: number; revision: number }
export interface Refund { id: string; reason: string; reply: string; status: 'requested' | 'processing' | 'success' | 'closed' | 'abnormal' | 'rejected'; revision: number; created_at: number; updated_at: number; completed_at: number | null }
export interface Order { id: string; plan_id: string; plan_name: string; plan_days: number; amount_fen: number; currency: string; status: 'created' | 'pending' | 'paid' | 'closed' | 'refunded'; created_at: number; expires_at: number; paid_at: number | null; revision: number; refund: Refund | null }
export interface PaymentParameters { timeStamp: string; nonceStr: string; package: string; signType: 'RSA'; paySign: string }
export const orderStatus = { created: '待付款', pending: '待确认付款', paid: '已付款', closed: '已关闭', refunded: '已退款' }
export const refundStatus = { requested: '退款待审核', processing: '退款处理中', success: '退款成功', closed: '退款已关闭', abnormal: '退款需人工处理', rejected: '退款未通过' }
export const yuan = (fen: number) => '¥' + (fen / 100).toFixed(2)
export const fetchPlans = () => request<{ items: Plan[]; checkout_enabled: boolean; ios_enabled: boolean }>('/api/v1/mini/membership/plans')
export const redeemMembershipCard = (code: string) => request<{ user: import('../types').User; days: number; vip_expires_at: number | null }>('/api/v1/mini/membership/redeem', 'POST', { code })
export const createOrder = (plan: Plan, request_id: string) => request<Order>('/api/v1/mini/orders', 'POST', { plan_id: plan.id, plan_revision: plan.revision, request_id })
export const fetchOrders = (offset = 0) => request<Page<Order>>('/api/v1/mini/orders?offset=' + offset)
export const fetchOrder = (id: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id))
export const payOrder = (id: string) => request<{ order: Order; payment: PaymentParameters | null }>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/pay', 'POST')
export const syncOrder = (id: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/sync', 'POST')
export const cancelOrder = (id: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/cancel', 'POST')
export const requestRefund = (id: string, reason: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/refund', 'POST', { reason })
export const syncRefund = (id: string) => request<Order>('/api/v1/mini/refunds/' + encodeURIComponent(id) + '/sync', 'POST')
export function openRequests(filters: { q?: string; grade?: string; subject?: string } = {}) {
  uni.navigateTo({ url: '/pages/requests/index?' + queryString({ title: filters.q, grade: filters.grade, subject: filters.subject }) })
}
export function openOrder(id: string) { uni.navigateTo({ url: '/pages/orders/index?id=' + encodeURIComponent(id) }) }
export function openTopic(id: string) { uni.navigateTo({ url: '/pages/topic/index?id=' + encodeURIComponent(id) }) }
