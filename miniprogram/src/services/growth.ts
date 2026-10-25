import { navigatePage } from './page-navigation'
import { reactive } from 'vue'
import { authGeneration, queryString, request, type ReadOptions } from './api'
import { devicePlatform } from './platform'
import { createUnreadTracker } from './unread-tracker'
import { safeDestination } from './return-route'

export interface Page<T> { items: T[]; total: number; has_more: boolean }
export type TagKind = 'textbook' | 'term' | 'unit' | 'knowledge'
export interface CatalogTag { id: string; kind: TagKind; name: string; paper_count?: number }
export const tagKinds: { kind: TagKind; label: string }[] = [{ kind: 'textbook', label: '教材' }, { kind: 'term', label: '学期' }, { kind: 'unit', label: '单元' }, { kind: 'knowledge', label: '知识点' }]
export type TagFilters = Record<TagKind, string>
export const emptyTags = (): TagFilters => ({ textbook: '', term: '', unit: '', knowledge: '' })
export const fetchTags = (options: ReadOptions = {}) => request<{ items: CatalogTag[] }>('/api/v1/site/catalog-tags', 'GET', undefined, options)
export interface Message { id: string; kind: string; title: string; body: string; target_type: string; target_id: string; read_at: number | null; created_at: number }
export const inboxState = reactive({ unread: 0, pending: 0 })
export const unreadTracker = createUnreadTracker(authGeneration, count => { inboxState.unread = count })
export const fetchMessages = (unread = false, offset = 0, limit = 20, options: ReadOptions = {}) => request<Page<Message> & { unread: number }>('/api/v1/mini/messages?' + queryString({ unread, offset, limit }), 'GET', undefined, options)
export async function refreshUnread(options: ReadOptions = {}) {
  const apply = unreadTracker.read()
  const result = await fetchMessages(false, 0, 1, options)
  apply(result.unread, inboxState.pending)
}
export async function readMessages(id = '', remainingPending: () => number = () => 0) {
  const finish = unreadTracker.write()
  try {
    const result = await request<{ unread: number }>('/api/v1/mini/messages/' + (id ? encodeURIComponent(id) + '/read' : 'read-all'), 'POST')
    return finish(result.unread, remainingPending())
  } catch (error) { finish(); throw error }
}
export function messageDestination(message: Pick<Message, 'target_type' | 'target_id'>) {
  const pages: Record<string, string> = { paper: 'paper', feedback: 'support', membership: 'membership', request: 'requests', closure: 'closure', order: 'orders' }
  const page = pages[message.target_type]
  return safeDestination(page ? '/pages/' + page + '/index' + (message.target_id ? '?id=' + encodeURIComponent(message.target_id) : '') : '/subpages/messages/index')
}
export const subscriptionConfig = (options: ReadOptions = {}) => request<{ available: boolean; template_id: string }>('/api/v1/mini/message-subscription', 'GET', undefined, options)
export const grantSubscription = (template_id: string, request_id: string) => request('/api/v1/mini/message-subscription', 'POST', { template_id, request_id })
export function requestKey() { return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 14) }
export interface ResourceRequest { id: string; title: string; grade: string; subject: string; details: string; status: 'pending' | 'planned' | 'fulfilled' | 'closed'; reply: string; catalog_id: string | null; paper_title?: string | null; revision: number; created_at: number; updated_at: number }
export const requestStatus = { pending: '待处理', planned: '已安排', fulfilled: '资料已补齐', closed: '已关闭' }
export const fetchRequests = (offset = 0, options: ReadOptions = {}) => request<Page<ResourceRequest>>('/api/v1/mini/requests?offset=' + offset, 'GET', undefined, options)
export const fetchResourceRequest = (id: string, options: ReadOptions = {}) => request<ResourceRequest>('/api/v1/mini/requests/' + encodeURIComponent(id), 'GET', undefined, options)
export const submitRequest = (body: { title: string; grade: string; subject: string; details: string }) => request<ResourceRequest>('/api/v1/mini/requests', 'POST', body)
export interface Closure { id: string; reason: string; status: 'pending' | 'cancelled' | 'rejected' | 'completed'; reply: string; revision: number; updated_at: number }
export const closureStatus = { pending: '等待审核', cancelled: '已撤回', rejected: '审核未通过', completed: '已注销' }
export const fetchClosure = (options: ReadOptions = {}) => request<{ request: Closure | null }>('/api/v1/mini/closure', 'GET', undefined, options)
export const applyClosure = (reason: string) => request<{ request: Closure }>('/api/v1/mini/closure', 'POST', { reason, acknowledge: true })
export const cancelClosure = (revision: number) => request<{ request: Closure }>('/api/v1/mini/closure?revision=' + revision, 'DELETE')
export interface Plan { id: string; name: string; description: string; days: number; price_fen: number; revision: number; virtual_product_id?: string; price_fen_ios?: number; ios_available?: boolean; purchase_limit?: number; purchased?: number; pending?: number; pending_order?: string | null; pending_expires_at?: number | null }
export interface Refund { id: string; reason: string; reply: string; status: 'requested' | 'processing' | 'success' | 'closed' | 'abnormal' | 'rejected'; revision: number; created_at: number; updated_at: number; completed_at: number | null }
export type PaymentChannel = 'wechat' | 'virtual'
export interface Order { id: string; plan_id: string; plan_name: string; plan_days: number; amount_fen: number; currency: string; status: 'created' | 'pending' | 'paid' | 'closed' | 'refunded'; payment_channel?: PaymentChannel; created_at: number; expires_at: number; paid_at: number | null; revision: number; refund: Refund | null }
export interface PaymentParameters { timeStamp: string; nonceStr: string; package: string; signType: 'RSA'; paySign: string }
export interface VirtualPaymentParameters { mode: 'short_series_goods'; signData: string; paySig: string; signature: string }
export type CheckoutPayment = PaymentParameters | VirtualPaymentParameters
export { orderLabels as orderStatus, refundLabels as refundStatus } from '../../../shared/commerce'
export const yuan = (fen: number) => '¥' + (fen / 100).toFixed(2)
export const fetchPlans = (options: ReadOptions = {}) => request<{ items: Plan[]; checkout_enabled: boolean; ios_enabled: boolean; checkout_channel?: PaymentChannel }>('/api/v1/mini/membership/plans', 'GET', undefined, options)
export const redeemMembershipCard = (code: string) => request<{ user: import('../types').User; days: number; vip_expires_at: number | null }>('/api/v1/mini/membership/redeem', 'POST', { code })
export const createOrder = (plan: Plan, request_id: string) => request<Order>('/api/v1/mini/orders', 'POST', { plan_id: plan.id, plan_revision: plan.revision, request_id, platform: devicePlatform() })
export const fetchOrders = (offset = 0, options: ReadOptions = {}) => request<Page<Order>>('/api/v1/mini/orders?offset=' + offset, 'GET', undefined, options)
export const fetchOrder = (id: string, options: ReadOptions = {}) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id), 'GET', undefined, options)
export const payOrder = (id: string) => request<{ order: Order; payment: CheckoutPayment | null }>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/pay', 'POST')
export const refreshWechatSession = (code: string) => request<{ refreshed: boolean }>('/api/v1/mini/wechat/session', 'POST', { code })
export const syncOrder = (id: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/sync', 'POST')
export const cancelOrder = (id: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/cancel', 'POST')
export const requestRefund = (id: string, reason: string) => request<Order>('/api/v1/mini/orders/' + encodeURIComponent(id) + '/refund', 'POST', { reason })
export const syncRefund = (id: string) => request<Order>('/api/v1/mini/refunds/' + encodeURIComponent(id) + '/sync', 'POST')
export function openRequests(filters: { q?: string; grade?: string; subject?: string } = {}) {
  navigatePage({ url: '/subpages/requests/index?' + queryString({ title: filters.q, grade: filters.grade, subject: filters.subject }) })
}
export function openOrder(id: string) { navigatePage({ url: '/subpages/orders/index?id=' + encodeURIComponent(id) }) }
export function openTopic(id: string) { navigatePage({ url: '/pages/topic/index?id=' + encodeURIComponent(id) }) }
