import { request } from './api'
import { change } from './growth'
import { downloadBlob } from '../../shared/download'
import type { SettlementApplication, Statement, SettlementKind } from './settlements'

const base = '/api/v1/admin/settlements'
export type SettlementTiming = '' | 'stalled' | 'review_overdue' | 'payout_overdue'
export interface SettlementFilters { admin_id?: string; q?: string; status?: string; channel?: string; start_date?: string; end_date?: string; date_basis?: 'created' | 'paid'; timing?: SettlementTiming }
export const query = (filters: SettlementFilters) => new URLSearchParams(Object.entries(filters).filter(([, value]) => value != null && value !== '') as [string, string][]).toString()
export interface SummaryValue { count: number; amount_fen: number; unknown?: number }
export interface SettlementSummary { available: SummaryValue; holding: SummaryValue; exception: SummaryValue; pending: SummaryValue; reviewing: SummaryValue; approved: SummaryValue; paid: SummaryValue; overdue: number; stalled?: number; review_overdue?: number; payout_overdue?: number }
export const settlementSummary = (filters: SettlementFilters) => request<SettlementSummary>(base + '/summary?' + query(filters))
export const settlementAdmins = () => request<{ items: { id: number; username: string }[] }>(base + '/admins')
export async function exportWorkbook(kind: SettlementKind, filters: SettlementFilters) { downloadBlob(await request<Blob>(base + '/export.xlsx?kind=' + kind + '&' + query(filters), undefined, 'blob'), '推广结算明细.xlsx') }
export interface Payee { name: string; method: 'bank' | 'wechat' | 'alipay'; account: string; bank: string; revision: number }
export const payeeMethods = { bank: '银行转账', wechat: '微信转账', alipay: '支付宝转账' }
export const loadPayee = () => request<Payee | null>(base + '/payee')
export const savePayee = (actor: number, value: Payee) => change<Payee>(base + '/payee', actor, value, 'PUT')
export const revealPayee = (actor: number, id: string) => change<Payee>(base + '/statements/' + id + '/payee/reveal', actor, {})
export const attachPayee = (actor: number, item: Statement) => change<Statement>(base + '/statements/' + item.id + '/payee', actor, { revision: item.revision })
export interface AuditEntry { id: number; kind: string; target: string; actor_name?: string; created_at: number; value: { reason?: string; difference_reason?: string; evidence?: string; order_ids?: string[]; source_request_id?: string; new_request_id?: string; name?: string } }
export const auditLabels: Record<string, string> = { apply_settlement: '提交结算申请', start_settlement_review: '开始对账', costs: '核对订单费用', batch_confirm_costs: '批量核对订单费用', create_statement: '生成结算单', approve: '审核应付金额', record_payout: '登记付款', void_statement: '作废结算单', settlement_request_rejected: '退回申请', settlement_request_invalidated: '申请失效', settlement_request_cancelled: '撤回申请', request_recovered: '剔除异常后重新申请', recovery_created: '已生成关联的新申请', attachment_added: '添加付款凭证', payee_attached: '留存收款资料', payee_revealed: '查看完整收款账号', adjustment: '登记历史调整', revoke_reward: '撤销订单奖励' }
Object.assign(auditLabels, { dispute_created: '提交结算异议', dispute_replied: '异议回复与处理', dispute_attachment: '补充异议凭据', monthly_archived: '留档月度对账单', payout_batch_created: '创建付款批次', payout_batch_imported: '登记批次回单', payout_batch_cancelled: '取消付款批次' })
export interface Attachment { id: string; name: string; media_type: string; created_at: number }
export interface BillDifference { order_id: string; reasons: string[] }
export const statementDetail = (id: string) => request<{ statement: Statement; payout_batch_id?: string | null; attachments: Attachment[]; timeline: AuditEntry[]; bill_differences?: BillDifference[]; operation_issues?: (BillDifference & { purpose?: 'review' | 'payment' })[] }>(base + '/statements/' + id)
export async function uploadEvidence(actor: number, id: string, file: File) {
  if (file.size > 2 * 1024 * 1024) throw new Error('凭证限 2MB')
  return request<{ id: string }>(base + '/statements/' + id + '/attachments?name=' + encodeURIComponent(file.name), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Workspace-User': String(actor) }, body: file })
}
export async function downloadEvidence(item: Attachment) { downloadBlob(await request<Blob>(base + '/attachments/' + item.id, undefined, 'blob'), item.name) }
export interface RecoveryPreview { order_ids: string[]; excluded: { order_id: string; reason: string }[]; revision: number }
export const recoveryPreview = (id: string) => request<RecoveryPreview>(base + '/requests/' + id + '/recover')
export const recoverApplication = (actor: number, item: SettlementApplication, reason: string) => change<SettlementApplication>(base + '/requests/' + item.id + '/recover', actor, { revision: item.revision, reason, confirmed: true })
export interface BillCheck { order_id: string; bill_row_id: number | null; channel_fee_fen: number | null; confirmed_fee_fen: number | null; fee_difference: boolean; differences: string[]; can_adopt: boolean; wechat_reconciliation: { id: string; differences: string[] } | null }
export interface BillImport { id: string; name: string; evidence: string; created_at: number; orders: number }
export interface BillRow { id: number; order_id: string; channel_label: string; amount_fen: number; channel_fee_fen: number; refunded_fen: number; check: BillCheck | null }
export const billImports = () => request<{ items: BillImport[] }>(base + '/bills')
export const billDetails = (id: string) => request<{ items: BillRow[] }>(base + '/bills/' + id)
export const importBill = (actor: number, value: { name: string; evidence: string; content: string }) => change<{ id: string; orders: number; duplicate: boolean }>(base + '/bills', actor, value)
export async function billTemplate() { downloadBlob(await request<Blob>(base + '/bills/template', undefined, 'blob'), '渠道账单模板.csv') }
export interface Notices { unread: number; last_id: number; items: Pick<AuditEntry, 'id' | 'kind' | 'target' | 'created_at'>[] }
export const notices = (personal = false) => request<Notices>(base + '/notices' + (personal ? '?personal=true' : ''))
export const readNotices = (actor: number, through: number, personal = false) => change(base + '/notices/read?through=' + through + (personal ? '&personal=true' : ''), actor, {})
export interface Difference { items: { order_id: string; before_fen: number | null; after_fen: number | null; channel_before_fen: number | null; channel_after_fen: number | null; fees: { name: string; before_fen: number | null; after_fen: number | null }[] }[]; reference_gross_fen: number | null; actual_gross_fen: number | null; adjustment_before_fen: number; adjustment_after_fen: number | null; reason: string }
