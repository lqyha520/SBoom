import { request } from './api'
import { change } from './growth'
import { downloadBlob } from '../../shared/download'
import type { UserInfo } from './api'
import { query, type Attachment, type SettlementFilters } from './settlement-operations'

const base = '/api/v1/admin/settlements'
export function financeGrant(user: UserInfo, stage: 'Costs' | 'Review' | 'Payout', action = 'run') {
  const grants = user.admin_permissions?.['settlement' + stage] ?? []
  return !!user.is_super_admin || grants.includes('view') && grants.includes(action)
}
export const financeUser = (user: UserInfo) => (['Costs', 'Review', 'Payout'] as const).some(stage => financeGrant(user, stage, 'view'))
/** 个人收益页面按本人展示，隐藏其另有的财务处理职责。 */
export const earningsUser = (user: UserInfo): UserInfo => ({ ...user, is_super_admin: false, admin_permissions: { ...user.admin_permissions, settlementCosts: [], settlementReview: [], settlementPayout: [] } })
export interface FinanceControls { revision: number; separate_review: boolean; separate_payment: boolean }
export const financeControls = () => request<FinanceControls>(base + '/finance-controls')
export const saveFinanceControls = (actor: number, value: FinanceControls) => change<FinanceControls>(base + '/finance-controls', actor, value, 'PUT')

export const ledgerLabels: Record<string, string> = { reward: '核定税前奖励', adjustment: '奖励调整', personal: '个人费用', tax: '代扣个税', payment: '已付款', void_reward: '作废核定奖励', void_personal: '作废个人费用', void_tax: '作废个税' }
export interface MonthlyReport { admin_id: number; admin_name: string; month: string; quote_digest: string; opening_fen: number; closing_fen: number; totals: Record<string, number>; archive_id: string | null; archived_at?: number; as_of: number; items: { source: string; statement_id: string; kind: string; amount_fen: number; occurred_at: number; original_at?: number }[] }
const monthlyQuery = (admin: string, month: string) => new URLSearchParams({ admin_id: admin, month }).toString()
export const monthlyReport = (admin: string, month: string) => request<MonthlyReport>(base + '/monthly?' + monthlyQuery(admin, month))
export const archiveMonthly = (actor: number, report: MonthlyReport) => change<MonthlyReport>(base + '/monthly/archive', actor, { admin_id: report.admin_id, month: report.month, quote_digest: report.quote_digest })
export async function downloadMonthly(admin: string, month: string) { downloadBlob(await request<Blob>(base + '/monthly/export.xlsx?' + monthlyQuery(admin, month), undefined, 'blob'), `推广月度对账-${month}.xlsx`) }

export interface PayoutBatchItem { statement_id: string; status: 'pending' | 'failed' | 'paid' | 'cancelled'; statement_status: string; reason: string; receipt: string; snapshot: { revision: number; amount_fen: number; beneficiary_name: string; payee: { name: string; account: string; method: string } | null } }
export interface PayoutBatch { id: string; name: string; status: 'active' | 'completed' | 'cancelled'; revision: number; created_at: number; total_fen: number; items: PayoutBatchItem[] }
export interface PayoutBatchSummary extends Omit<PayoutBatch, 'items'> { item_count: number; items?: PayoutBatchItem[] }
export interface PayoutMatch { items: { statement_id: string; status: string; amount_fen: number | null; receipt: string; issues: string[] }[]; matched: number; blocked: number }
export interface PayoutImportResult { paid: number; failed: number; pending: number; blocked: number; duplicate?: boolean; issues: { statement_id: string; reasons: string[] }[] }
export const payoutBatches = (page: number, filters: { q?: string; status?: string } = {}) => request<{ items: PayoutBatchSummary[]; total: number }>(base + '/batches?' + new URLSearchParams({ page: String(page), ...filters }))
export const payoutBatch = (id: string) => request<PayoutBatch>(base + '/batches/' + encodeURIComponent(id))
export const createPayoutBatch = (actor: number, name: string, ids: string[], key: string) => change<PayoutBatch>(base + '/batches', actor, { name, statement_ids: ids, request_key: key })
export const previewPayoutImport = (id: string, content: string) => request<PayoutMatch>(base + '/batches/' + id + '/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) })
export const importPayoutReceipts = (actor: number, item: PayoutBatch, content: string) => change<PayoutImportResult>(base + '/batches/' + item.id + '/import', actor, { revision: item.revision, content, confirmed: true })
export const cancelPayoutBatch = (actor: number, item: PayoutBatch) => change<PayoutBatch>(base + '/batches/' + item.id + '/cancel', actor, { revision: item.revision })
export async function downloadPayoutBatch(id: string) { downloadBlob(await request<Blob>(base + '/batches/' + id + '/export.csv', undefined, 'blob'), '付款批次清单.csv') }

export type DisputeStatus = 'open' | 'processing' | 'resolved' | 'rejected'
export interface Dispute { id: string; beneficiary: string; target_kind: 'reward' | 'statement'; target_id: string; title: string; status: DisputeStatus; revision: number; created_at: number; messages: { id: number; actor_name: string; content: string; evidence: string; created_at: number }[]; files: Attachment[] }
export const disputeStatuses: Record<DisputeStatus, string> = { open: '待处理', processing: '处理中', resolved: '已解决', rejected: '不予采纳' }
export const disputes = (status: string, page: number, personal = false) => request<{ items: Dispute[]; total: number }>(base + '/disputes?' + new URLSearchParams({ status, page: String(page), ...(personal ? { personal: 'true' } : {}) }))
export const getDispute = (id: string, personal = false) => request<Dispute>(base + '/disputes/' + id + (personal ? '?personal=true' : ''))
export const createDispute = (actor: number, value: { target_kind: 'reward' | 'statement'; target_id: string; title: string; content: string; evidence: string; request_key: string }) => change<Dispute>(base + '/disputes', actor, value)
export const replyDispute = (actor: number, item: Dispute, content: string, evidence: string, status: DisputeStatus) => change<Dispute>(base + '/disputes/' + item.id + '/reply', actor, { revision: item.revision, content, evidence, status })
export async function uploadDisputeFile(actor: number, id: string, file: File) {
  if (file.size > 2 * 1024 * 1024) throw new Error('凭证限 2MB')
  return request(base + '/disputes/' + id + '/files?name=' + encodeURIComponent(file.name), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Workspace-User': String(actor) }, body: file })
}
export async function downloadDisputeFile(file: Attachment) { downloadBlob(await request<Blob>(base + '/dispute-files/' + file.id, undefined, 'blob'), file.name) }

export interface CampaignExpense { source_ref?: string; included_in_baseline?: boolean; id: string; revision: number; expense_date: string; category: string; amount_fen: number; evidence: string; note: string; active: boolean }
export interface ExpenseLedger { items: CampaignExpense[]; total: number; period_fen: number; baseline_fen: number | null; cumulative_fen: number | null; known_cumulative_fen?: number; admin_id?: number }
export interface FinanceExpense extends CampaignExpense { campaign_id: string; campaign_name: string; admin_id: number; admin_name: string; created_at: number }
export interface FinanceExpenseLedger { items: FinanceExpense[]; total: number; period_fen: number; baseline_fen: number; cumulative_fen: number; unknown_campaigns: number }
export interface FinanceExpenseFilters { admin_id?: string; campaign_id?: string; q?: string; start_date?: string; end_date?: string; state?: string }
const financeExpenseQuery = (filters: FinanceExpenseFilters & { page?: string }) => new URLSearchParams(Object.entries(filters).filter(([, value]) => !!value) as [string, string][])
export const financeExpenses = (filters: FinanceExpenseFilters & { page?: string }) => request<FinanceExpenseLedger>(base + '/expenses?' + financeExpenseQuery(filters))
export async function downloadFinanceExpenses(filters: FinanceExpenseFilters) { downloadBlob(await request<Blob>(base + '/expenses/export.xlsx?' + financeExpenseQuery(filters), undefined, 'blob'), '财务成本台账.xlsx') }
const expensePath = (id: string) => '/api/v1/admin/referrals/campaigns/' + id + '/expenses'
export const expenseLedger = (id: string, start: string, end: string, page: number) => request<ExpenseLedger>(expensePath(id) + '?' + new URLSearchParams({ start_date: start, end_date: end, page: String(page) }))
export function saveExpense(actor: number, campaign: string, value: Omit<CampaignExpense, 'id' | 'revision' | 'active'>, item?: CampaignExpense, requestKey?: string) {
  if (!item && !requestKey) throw new Error('投入草稿缺少请求编号，请刷新')
  return change<CampaignExpense>(expensePath(campaign) + (item ? '/' + item.id : ''), actor, item ? { ...value, revision: item.revision, active: item.active } : { ...value, request_key: requestKey }, item ? 'PUT' : 'POST')
}
export interface QualityRow { group_key: string; campaign_name: string; admin_name: string; days: number; observed_users: number; waiting_users: number; paying_users: number; renewing_users: number; refunded_users: number; net_fen: number; pay_rate_bps: number | null; renewal_rate_bps: number | null; value_per_user_fen: number | null }
export const referralQuality = (filters: SettlementFilters & { campaign_id?: string }, page: number) => request<{ as_of: number; items: QualityRow[]; total: number }>('/api/v1/admin/referrals/quality?' + query(filters) + '&page=' + page)

export type PayoutCandidate = import('./settlements').Statement & { payout_issues: string[]; batch_id?: string | null }
export interface PayoutSelection { items: PayoutCandidate[]; total_fen: number; blocked: number }
export const payoutCandidates = (page: number) => request<{ items: PayoutCandidate[]; total: number; page: number }>(base + '/payout-candidates?page=' + page)
export const previewPayoutSelection = (ids: string[]) => request<PayoutSelection>(base + '/payout-candidates/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ statement_ids: ids }) })
