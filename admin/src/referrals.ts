import { request } from './api'
import { change, yuan, type Order } from './growth'
import { downloadBlob } from '../../shared/download'
import type { Referral } from '../../shared/referral'
export { referralSource } from '../../shared/referral'
export type ReferralStage = 'all' | 'ordered' | 'paid' | 'not_ordered' | 'unpaid'
export const referralStages = [{ value: 'all', label: '全部注册用户' }, { value: 'not_ordered', label: '尚未下单' }, { value: 'unpaid', label: '下单未付' }, { value: 'paid', label: '曾付费' }, { value: 'ordered', label: '曾下单' }]
export interface ReferralUser { stage?: ReferralStage; last_order_at?: number | null; last_paid_at?: number | null; id: string; username: string; nickname: string; created_at: number; referral: Referral }
export interface ReferralSummary { first_paying_users?: number; first_paid_fen?: number; renewal_paid_fen?: number; reward_reference_fen?: number; reward_unknown?: number; reward_known?: number; after_reward_reference_fen?: number; registrations: number; orders: number; paying_users: number; paid_fen: number; refunded_fen: number; net_fen: number }
export function referenceRewardLabel(value: Pick<ReferralSummary, 'reward_reference_fen' | 'reward_unknown' | 'reward_known'>) {
  const amount = value.reward_reference_fen ?? 0, unknown = value.reward_unknown ?? 0
  if (!unknown) return yuan(amount)
  return (value.reward_known ?? (amount > 0 ? 1 : 0)) > 0 ? `已知小计 ${yuan(amount)}；另有 ${unknown} 笔待核对` : `待核对（${unknown} 笔）`
}
export interface Promoter { id: number; username: string; is_active: number }
export interface PromotionCode { code: string; admin_id: number; admin_name: string; path: string }
export interface ReferralAudit { id: number; actor_name: string | null; before_json: Referral; after_json: Referral; reason: string; created_at: number }
export interface ReferralFilters { stage?: string; as_of?: string; campaign_id?: string; date_basis?: 'created' | 'paid'; admin_id?: string; q?: string; start_date?: string; end_date?: string }
const base = '/api/v1/admin/referrals'
export function referralQuery(filters: ReferralFilters) { return new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== undefined && v !== '') as [string, string][]).toString() }
export const promoters = () => request<{ items: Promoter[] }>(base + '/admins')
export const promotionCode = (actor: number, admin_id?: number) => change<PromotionCode>(base + '/code', actor, { admin_id })
export const referralSummary = (filters: ReferralFilters) => request<ReferralSummary>(base + '/summary?' + referralQuery({ ...filters, stage: undefined, as_of: undefined }))
export const referralUsers = (filters: ReferralFilters, offset: number) => request<{ items: ReferralUser[]; total: number }>(base + '/users?' + referralQuery(filters) + '&offset=' + offset)
export const referralOrders = (filters: ReferralFilters, offset: number) => request<{ items: Order[]; total: number }>(base + '/orders?' + referralQuery({ ...filters, stage: undefined, as_of: undefined }) + '&offset=' + offset)
export async function exportReferrals(kind: 'users' | 'orders', filters: ReferralFilters) {
  const blob = await request<Blob>(base + '/export/' + kind + '?' + referralQuery(filters), undefined, 'blob')
  downloadBlob(blob, '推广' + (kind === 'users' ? '用户' : '订单') + '.csv')
}
export async function downloadPromotionCode(actor: number, admin_id: number, env_version: string) {
  const blob = await request<Blob>(base + '/qrcode', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(actor) }, body: JSON.stringify({ admin_id, env_version }) }, 'blob')
  downloadBlob(blob, '推广小程序码-' + admin_id + '.' + (blob.type.includes('jpeg') ? 'jpg' : 'png'))
}
export const supplementReferral = (actor: number, target: string, admin_id: number, reason: string) => change<Referral>(base + '/users/' + encodeURIComponent(target), actor, { admin_id, reason }, 'PUT')
export const referralAudit = (target: string) => request<{ items: ReferralAudit[] }>(base + '/users/' + encodeURIComponent(target) + '/audit')
