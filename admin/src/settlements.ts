import type { ServiceTerms } from './settlement-timing'
import { request } from './api'
import { change } from './growth'
import { downloadBlob } from '../../shared/download'
import { query, type SettlementFilters, type Payee, type Difference, type AuditEntry, type Attachment, type BillCheck } from './settlement-operations'

export interface Fee { name: string; amount_fen: number }
export type FeeBasis = 'order_gross' | 'after_channel'
export interface SharedFee { name: string; source_ref?: string; mode?: 'fixed' | 'percent'; amount_fen?: number; rate_bps?: number; basis?: FeeBasis; base_fen?: number }
export type PersonalFeeBasis = 'reward_gross' | 'after_adjustment'
export interface PersonalFee extends Omit<SharedFee, 'basis'> { basis?: PersonalFeeBasis }
export interface FeeDraft { name: string; source_ref?: string; amount: string; mode?: 'fixed' | 'percent'; rate?: string; basis?: FeeBasis | PersonalFeeBasis }
export interface ChannelRates { wechat: number; virtual_android: number; virtual_ios: number }
export interface ChannelTotal { key: string; label: string; orders: number; amount_fen: number; channel_fen: number | null; shared_fen: number | null; commission_fen: number | null; unknown_rates: number }
export interface RewardPolicy extends ServiceTerms { max_reward_fen?: number | null; revision: number; enabled: boolean; beneficiary: 'admin'; rate_bps: number; hold_days: number; channel_rate_bps?: number | null; channel_rates?: ChannelRates | null; shared_fees: SharedFee[] }
export interface Costs { bill_row_id?: number; channel_fee_fen: number; channel_rate_bps?: number; channel_base_fen?: number; channel_rounding?: 'half_up'; shared_fees: SharedFee[]; evidence: string; confirmed: true }
export interface Reward { eligibility_issue?: { code: 'inactive' | 'refund' | 'unpaid' | 'not_first' | 'holding' | 'earlier_order'; reason: string; order_id: string } | null; order_id: string; beneficiary: string; beneficiary_name: string; status: 'pending' | 'void' | 'paid'; application_state?: keyof typeof applicationEligibilityLabels; revision: number; policy: RewardPolicy; costs: Costs | null; commission_fen: number | null; statement_id: string | null; request_id?: string | null; reason: string; amount_fen: number; paid_at: number; available_at: number; refund_status: string | null; payment_channel: string; device_platform: string }
export interface Adjustment { id: number; beneficiary: string; beneficiary_name: string; amount_fen: number; reason: string; evidence: string; statement_id: string | null; source: string }
export interface Statement { approved_at?: number | null; payout?: { transferred_at?: number | null; registered_at?: number }; paid_at?: number; id: string; beneficiary: string; beneficiary_name: string; revision: number; status: 'draft' | 'approved' | 'paid' | 'void'; gross_fen: number; adjustment_fen: number; personal_fen: number; tax_fen: number | null; net_fen: number | null; reason: string; receipt: string; created_at: number; snapshot: { service_terms?: ServiceTerms; payee?: Payee; channels?: ChannelTotal[]; items: { order_id: string; amount_fen: number; payment_channel?: string; device_platform?: string; commission_fen: number; costs: Costs; policy: RewardPolicy }[]; adjustments: Adjustment[] }; review: { personal_fees: PersonalFee[]; tax_fen: number; evidence: string; difference_reason?: string } | null }
export type SettlementKind = 'rewards' | 'statements' | 'adjustments' | 'requests'
export const settlementStates = { pending: '待核对', draft: '待审核', approved: '待付款', paid: '已结算', void: '已作废' }
export const applicationEligibilityLabels = { available: '可申请', holding: '等待期内', exception: '异常待处理', requested: '已申请结算', statement: '已入结算单', paid: '已结算', void: '已失效' }
export function rewardApplicationState(item: Reward): keyof typeof applicationEligibilityLabels {
  if (item.application_state) return item.application_state
  if (item.status !== 'pending') return item.status
  if (item.statement_id) return 'statement'
  if (item.request_id) return 'requested'
  if (['requested', 'processing', 'abnormal', 'success'].includes(item.refund_status || '')) return 'exception'
  if (item.available_at > Date.now() / 1000) return 'holding'
  // 旧接口未返回完整资格时不在浏览器推断可申请；预览仍可由服务端核对。
  return 'exception'
}
const base = '/api/v1/admin/settlements'
export const rewardPolicy = () => request<RewardPolicy>(base + '/policy')
export const saveRewardPolicy = (actor: number, value: RewardPolicy & { reason: string }) => change<RewardPolicy>(base + '/policy', actor, value, 'PUT')
export const settlementList = <T>(kind: SettlementKind, offset: number, filters: SettlementFilters = {}) => request<{ items: T[]; total: number }>(base + '/list/' + kind + '?offset=' + offset + '&' + query(filters))
export const confirmRewardCosts = (actor: number, reward: Reward, value: Omit<Costs, 'channel_fee_fen'> & { channel_rate_bps: number }) => change<Reward>(base + '/rewards/' + reward.order_id + '/costs', actor, { ...value, revision: reward.revision }, 'PUT')
export const createStatement = (actor: number, order_ids: string[], beneficiary?: string, settlement_request_id?: string) => change<Statement>(base + '/statements', actor, { order_ids, beneficiary, settlement_request_id })
export const approveStatement = (actor: number, item: Statement, value: { personal_fees: PersonalFee[]; tax_fen: number; evidence: string; confirmed: true; difference_reason?: string }) => change<Statement>(base + '/statements/' + item.id + '/approve', actor, { ...value, revision: item.revision })
export const recordSettlementPayment = (actor: number, item: Statement, amount_fen: number, receipt: string, transferred_at?: number) => change<Statement>(base + '/statements/' + item.id + '/paid', actor, { revision: item.revision, amount_fen, receipt, transferred_at })
export const voidStatement = (actor: number, item: Statement, reason: string) => change<Statement>(base + '/statements/' + item.id + '/void', actor, { revision: item.revision, reason })
export const recordAdjustment = (actor: number, value: { beneficiary: string; amount_fen: number; reason: string; evidence: string; request_id: string }) => change<Adjustment>(base + '/adjustments', actor, value)
export async function exportSettlements() { downloadBlob(await request<Blob>(base + '/export', undefined, 'blob'), '推广结算.csv') }

/** 字符串转整数分，避免浮点截断及空值被默认为零。 */
export function moneyFen(value: string, signed = false): number {
  const text = String(value).trim()
  if (!(signed ? /^-?\d+(\.\d{1,2})?$/ : /^\d+(\.\d{1,2})?$/).test(text)) throw new Error('金额必填，最多两位小数')
  const [whole, fraction = ''] = text.replace('-', '').split('.')
  const result = (Number(whole) * 100 + Number(fraction.padEnd(2, '0'))) * (text.startsWith('-') ? -1 : 1)
  if (!Number.isSafeInteger(result) || Math.abs(result) > 100000000000) throw new Error('金额超出范围')
  return result
}
export function percentageBps(value: string): number {
  const result = moneyFen(value)
  if (result > 10000) throw new Error('比例必须在0%至100%之间，最多两位小数')
  return result
}
export const channelFeeFen = (amount: number, rate: number) => Math.floor((amount * rate + 5000) / 10000)
export function channelLabel(channel?: string, platform?: string): string {
  if (channel === 'wechat') return '普通微信支付'
  if (channel === 'virtual' && platform === 'ios') return '虚拟支付 · iOS'
  if (channel === 'virtual' && ['android', 'harmony', 'harmonyos', 'ohos', 'windows'].includes(platform ?? '')) return '虚拟支付 · 安卓/鸿蒙/Windows'
  return '渠道或设备待核对'
}
export const feeDrafts = (fees: SharedFee[]): FeeDraft[] => fees.map(fee => ({ ...(fee.source_ref ? { source_ref: fee.source_ref } : {}), ...(fee.mode === 'percent'
  ? { name: fee.name, mode: 'percent', rate: ((fee.rate_bps ?? 0) / 100).toFixed(2), basis: fee.basis ?? 'after_channel', amount: '' }
  : { name: fee.name, amount: ((fee.amount_fen ?? 0) / 100).toFixed(2) }) }))
export function feeValues(fees: FeeDraft[]): Fee[] {
  if (fees.some(fee => !fee.name.trim())) throw new Error('请填写每项费用的名称')
  if (fees.some(fee => fee.mode === 'percent')) throw new Error('个人费用请填写实际金额')
  return fees.map(fee => ({ name: fee.name.trim(), amount_fen: moneyFen(fee.amount) }))
}

export function sharedFeeValues(fees: FeeDraft[]): SharedFee[] {
  return fees.map(fee => {
    if (!fee.name.trim()) throw new Error('请填写每项费用的名称')
    if (fee.mode !== 'percent') return { ...(fee.source_ref?.trim() ? { source_ref: fee.source_ref.trim() } : {}), name: fee.name.trim(), amount_fen: moneyFen(fee.amount) }
    if (fee.basis && !['order_gross', 'after_channel'].includes(fee.basis)) throw new Error('请选择共同费用的计算基数')
    return { ...(fee.source_ref?.trim() ? { source_ref: fee.source_ref.trim() } : {}), name: fee.name.trim(), mode: 'percent', rate_bps: percentageBps(fee.rate ?? ''), basis: (fee.basis ?? 'after_channel') as FeeBasis }
  })
}

export const feeBasisNames: Record<FeeBasis, string> = { order_gross: '订单实收', after_channel: '扣支付手续费后金额' }
export const personalBasisNames: Record<PersonalFeeBasis, string> = { reward_gross: '税前奖励合计', after_adjustment: '历史调整后可用奖励' }
export function personalFeeValues(fees: FeeDraft[]): PersonalFee[] {
  return fees.map(fee => {
    if (!fee.name.trim()) throw new Error('请填写每项费用的名称')
    if (fee.mode !== 'percent') return { ...(fee.source_ref?.trim() ? { source_ref: fee.source_ref.trim() } : {}), name: fee.name.trim(), amount_fen: moneyFen(fee.amount) }
    if (fee.basis && !['reward_gross', 'after_adjustment'].includes(fee.basis)) throw new Error('请选择个人费用的计算基数')
    return { ...(fee.source_ref?.trim() ? { source_ref: fee.source_ref.trim() } : {}), name: fee.name.trim(), mode: 'percent', rate_bps: percentageBps(fee.rate ?? ''), basis: (fee.basis ?? 'reward_gross') as PersonalFeeBasis }
  })
}
export function resolvePersonalFees(fees: PersonalFee[], gross: number, adjustment: number) {
  return fees.map(fee => {
    const base = fee.basis === 'after_adjustment' ? Math.max(0, gross + adjustment) : gross
    return { ...fee, base_fen: fee.base_fen ?? base, amount_fen: fee.mode === 'percent'
      ? fee.base_fen != null && fee.amount_fen != null ? fee.amount_fen : Math.floor(base * (fee.rate_bps ?? 0) / 10000)
      : fee.amount_fen ?? 0 }
  })
}

/** 与服务端相同：每项费用及单笔奖励各自舍去不足一分，不按费用顺序叠乘。 */
export function calculateReward(amount: number, channel: number, fees: SharedFee[], rate: number, cap?: number | null) {
  const afterChannel = Math.max(0, amount - channel)
  const resolved = fees.map(fee => {
    const base = fee.basis === 'order_gross' ? amount : afterChannel
    return { ...fee, base_fen: fee.base_fen ?? base,
      amount_fen: fee.mode === 'percent' ? fee.base_fen !== undefined && fee.amount_fen !== undefined
        ? fee.amount_fen : Math.floor(base * (fee.rate_bps ?? 0) / 10000) : fee.amount_fen ?? 0 }
  })
  const shared = resolved.reduce((sum, fee) => sum + fee.amount_fen, 0)
  const distributable = Math.max(0, amount - channel - shared)
  return { afterChannel, fees: resolved, shared, distributable, commission: Math.min(Math.floor(distributable * rate / 10000), cap ?? Infinity) }
}

/** 展示本单核对快照或下单规则；不套用当前全局费率，不把未知渠道费当成零。 */
export function rewardCalculation(item: Pick<Reward, 'amount_fen' | 'costs' | 'policy' | 'commission_fen'>) {
  const channelRate = (item.costs ? item.costs.channel_rate_bps : item.policy.channel_rate_bps) ?? null
  const channel = item.costs?.channel_fee_fen ?? (channelRate === null ? null : channelFeeFen(item.amount_fen, channelRate))
  const fees = item.costs?.shared_fees ?? item.policy.shared_fees
  const calculated = channel === null ? null : calculateReward(item.amount_fen, channel, fees, item.policy.rate_bps, item.policy.max_reward_fen)
  return { amount: item.amount_fen, channel, channelRate, fees: calculated?.fees ?? fees, rate: item.policy.rate_bps,
    commission: item.costs ? item.commission_fen : calculated?.commission ?? null, estimated: !item.costs, cap: item.policy.max_reward_fen }
}

// 起步建议，不代表行业统一标准或实际发生费用；使用前仍需核对并保存。
export const starterPolicy = () => ({ rate_bps: 1000, hold_days: 14, channel_rate_bps: 60,
  channel_rates: { wechat: 60, virtual_android: 100, virtual_ios: 1200 },
  shared_fees: [{ name: '服务成本分摊', mode: 'percent', rate_bps: 0, basis: 'after_channel' }] as SharedFee[] })

export interface ApplicationSnapshot {
  service_terms?: ServiceTerms
  source_request_id?: string; recovery_excluded?: { order_id: string; reason: string }[]
  all_eligible?: boolean;
  channels?: ChannelTotal[]; excluded?: { order_id: string; reason: string; available_at: number }[]
  items: { order_id: string; revision: number; amount_fen: number; payment_channel?: string; device_platform?: string; policy: RewardPolicy; costs: Costs | null; reference_channel_fen: number | null; reference_channel_rate_bps?: number | null; reference_fees: SharedFee[]; reference_commission_fen: number | null }[]
  adjustments: Adjustment[]; reference_gross_fen: number | null; adjustment_fen: number; reference_after_adjustment_fen: number | null; unconfirmed_orders: number
  unknown_orders?: number; known_reference_gross_fen?: number
  personal_fen: null; tax_fen: null; net_fen: null
}
export interface ApplicationQuote { snapshot: ApplicationSnapshot; quote_digest: string }
export interface SettlementApplication extends ApplicationQuote {
  confirmed_orders?: number
  statement_summary?: Pick<Statement, 'id' | 'status' | 'gross_fen' | 'personal_fen' | 'tax_fen' | 'net_fen' | 'receipt' | 'approved_at'> | null
  id: string; beneficiary: string; beneficiary_name: string; revision: number; status: 'pending' | 'reviewing' | 'approved' | 'paid' | 'rejected' | 'cancelled' | 'invalidated'
  request_key: string; note: string; reason: string; statement_id: string | null; created_at: number; updated_at: number
}
export interface ApplicationDetail { request: SettlementApplication; rewards: Reward[]; statement: Statement | null; difference?: Difference; timeline?: AuditEntry[]; attachments?: Attachment[]; bill_checks?: BillCheck[] }
export const applicationStates = { pending: '待对账', reviewing: '对账中', approved: '待付款', paid: '已结算', rejected: '已退回', cancelled: '已撤回', invalidated: '已失效' }
export const previewApplication = (order_ids: string[], all_eligible = false) => request<ApplicationQuote>(base + '/requests/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(all_eligible ? { all_eligible } : { order_ids }) })
export const applySettlement = (actor: number, value: { order_ids?: string[]; all_eligible?: boolean; request_key: string; quote_digest: string; note: string; confirmed: true }) => change<SettlementApplication>(base + '/requests', actor, value)
export const applicationDetail = (id: string) => request<ApplicationDetail>(base + '/requests/' + id)
export const startApplication = (actor: number, item: SettlementApplication) => change<SettlementApplication>(base + '/requests/' + item.id + '/start', actor, { revision: item.revision })
export const confirmApplicationCosts = (actor: number, item: SettlementApplication, items: { order_id: string; revision: number; channel_rate_bps?: number; channel_fee_fen?: number; bill_row_id?: number; shared_fees: SharedFee[]; evidence: string; confirmed: true }[]) => change<SettlementApplication>(base + '/requests/' + item.id + '/costs', actor, { revision: item.revision, items }, 'PUT')
export const closeApplication = (actor: number, item: SettlementApplication, reason: string, cancel = false) => change<SettlementApplication>(base + '/requests/' + item.id + (cancel ? '/cancel' : '/reject'), actor, { revision: item.revision, reason })
