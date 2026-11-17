<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { navigateAdmin, useAdminListRoute, type AdminTab } from '../navigation'
import { canPermission, permissionDirective as vPermission } from '../permissions'
import { dateTime, yuan } from '../growth'
import { applicationEligibilityLabels, rewardApplicationState, approveStatement, calculateReward, channelFeeFen, channelLabel, confirmRewardCosts, createStatement, feeDrafts, personalFeeValues, resolvePersonalFees, moneyFen, percentageBps, recordAdjustment, rewardCalculation, rewardPolicy, saveRewardPolicy, sharedFeeValues, settlementList, settlementStates, starterPolicy, voidStatement, type Adjustment, type FeeDraft, type Reward, type RewardPolicy, type SettlementKind, type Statement } from '../settlements'
import SettlementFees from './SettlementFees.vue'
import SettlementChannels from './SettlementChannels.vue'
import RewardCalculation from './RewardCalculation.vue'
import SettlementCalculation from './SettlementCalculation.vue'
import SettlementApplyDialog from './SettlementApplyDialog.vue'
import SettlementRequests from './SettlementRequests.vue'
import SettlementTarget from './SettlementTarget.vue'
import type { SettlementApplication } from '../settlements'
import { settlementSummary, settlementAdmins, exportWorkbook, type SettlementSummary, type SettlementFilters, type SettlementTiming } from '../settlement-operations'
import SettlementOverview from './SettlementOverview.vue'
import SettlementPromoterOverview from './SettlementPromoterOverview.vue'
import ReferralRules from './ReferralRules.vue'
import { processingDays } from '../settlement-timing'
import SettlementPayee from './SettlementPayee.vue'
import SettlementNotices from './SettlementNotices.vue'
import SettlementEvidence from './SettlementEvidence.vue'
import PromotionTabs from './PromotionTabs.vue'
import PromotionActions from './PromotionActions.vue'
import PromotionStatus from './PromotionStatus.vue'
import SettlementMonthly from './SettlementMonthly.vue'
import SettlementDisputes from './SettlementDisputes.vue'
import { earningsUser, financeGrant, financeUser } from '../promotion-finance'
import '../promotion-layout.css'

const props = defineProps<{ user: UserInfo; mode?: 'finance' | 'personal' | 'rules'; routeTab?: AdminTab }>()
const finance = computed(() => props.mode ? props.mode === 'finance' : financeUser(props.user))
const viewUser = computed(() => finance.value ? props.user : earningsUser(props.user))
const canCosts = computed(() => finance.value && financeGrant(props.user, 'Costs')), canReview = computed(() => finance.value && financeGrant(props.user, 'Review')), canPayout = computed(() => finance.value && financeGrant(props.user, 'Payout'))
const requestedDispute = ref(new URLSearchParams(location.hash.split('?')[1] || '').get('dispute') || '')
const disputeTarget = ref<{ kind: 'reward' | 'statement'; id: string } | null>(null)
function dispute(kind: 'reward' | 'statement', id: string) { requestedDispute.value = ''; disputeTarget.value = { kind, id }; section.value = 'disputes' }
const section = ref(props.mode === 'rules' ? 'rules' : 'workspace'), unreadNotices = ref(0)
const sections = computed(() => props.mode === 'rules' ? [{ value: 'rules', label: '奖励规则' }] : [
  { value: 'workspace', label: finance.value ? '结算工作台' : '我的收益' },
  ...(!finance.value ? [{ value: 'monthly', label: '月度对账' }] : []),
  { value: 'disputes', label: '结算异议' },
  ...(!finance.value && canApply.value ? [{ value: 'payee', label: '收款资料' }] : []),
  { value: 'notices', label: '结算提醒', badge: unreadNotices.value },
  ...(!finance.value ? [{ value: 'rules', label: '奖励规则' }] : []),
])
const activeSection = computed(() => sections.value.some(item => item.value === section.value) ? section.value : 'workspace')
const kind = ref<SettlementKind>(finance.value ? 'requests' : 'rewards'), pageNumber = ref(1), total = ref(0)
const admin = ref(''), q = ref(''), status = ref(''), channel = ref(''), start = ref(''), end = ref('')
const dateBasis = ref<'created' | 'paid'>('created'), timing = ref<SettlementTiming>(''), reviewBlocked = ref(true)
const summary = ref<SettlementSummary | null>(null), accounts = ref<{ id: number; username: string }[]>([])
const cap = ref(''), differenceReason = ref(''), evidenceBusy = ref(false)
const filters = (): SettlementFilters => ({ admin_id: finance.value ? admin.value : String(props.user.id), q: q.value, status: status.value, channel: channel.value, start_date: start.value, end_date: end.value, date_basis: dateBasis.value, timing: timing.value })
const stateOptions = computed(() => {
  const values = kind.value === 'rewards' ? { available: '可申请', holding: '等待期内', exception: '异常待处理', pending: '待结算', paid: '已结算', void: '已失效' }
    : kind.value === 'requests' ? { pending: '待对账', reviewing: '对账中', approved: '待付款', paid: '已结算', rejected: '已退回', cancelled: '已撤回', invalidated: '已失效' }
      : kind.value === 'statements' ? { draft: '待审核', approved: '待付款', paid: '已付款', void: '已作废' } : { open: '待抵扣或补付', settled: '已入结算单' }
  return [{ value: '', label: '全部状态' }, ...Object.entries(values).map(([value, label]) => ({ value, label }))]
})
function search() {
  if (start.value && end.value && start.value > end.value) { error.value = '起始日期不能晚于截止日期'; return }
  selected.value = []; if (pageNumber.value !== 1) pageNumber.value = 1; else void page.load()
}
function resetFilters() { admin.value = ''; q.value = ''; status.value = ''; channel.value = ''; start.value = ''; end.value = ''; dateBasis.value = 'created'; timing.value = ''; search() }
function selectScope(next: SettlementKind, state: string, word?: string) { section.value = 'workspace'; status.value = state; timing.value = ''; if (word !== undefined) q.value = word; if (kind.value === next) search(); else { kind.value = next; nextStatus = state } }
function selectTiming(value: SettlementTiming) {
  selectScope('requests', '')
  timing.value = value; search()
}
let nextStatus: string | null = null
const rewards = ref<Reward[]>([]), statements = ref<Statement[]>([]), adjustments = ref<Adjustment[]>([]), selected = ref<string[]>([])
const applications = ref<SettlementApplication[]>([]), applyOpen = ref(false), applyIds = ref<string[]>([])
const applyAllEligible = ref(false), requestRefresh = ref(0)
const androidRate = ref(''), iosRate = ref(''), reviewDays = ref(''), payoutDays = ref('')
const exampleChannel = ref<'wechat' | 'virtual_android' | 'virtual_ios'>('wechat')
const canApply = computed(() => canPermission('settlements:create'))
const canSelect = computed(() => canCosts.value || canApply.value && !finance.value)
const policy = ref<RewardPolicy | null>(null), enabled = ref(false), rate = ref(''), holdDays = ref(7), defaults = ref<FeeDraft[]>([]), policyReason = ref('')
const dialog = ref(false), action = ref('costs'), reward = ref<Reward | null>(null), statement = ref<Statement | null>(null)
const channelRate = ref(''), defaultChannelRate = ref(''), fees = ref<FeeDraft[]>([]), tax = ref(''), evidence = ref(''), confirmed = ref(false), amount = ref(''), reason = ref('')
const beneficiary = ref(''), beneficiaryName = ref(''), adjustmentRequest = ref('')
const exampleAmount = ref('100.00')
const rewardRows = computed(() => rewards.value.map(item => ({ ...item, calculation: rewardCalculation(item) })))
const rewardDetail = computed(() => reward.value ? rewardCalculation(reward.value) : null)
const title = computed(() => ({ costs: '核对订单共同费用', review: '核对个人费用与税费', detail: '结算单明细', reward_detail: '订单奖励计算明细', void: '作废结算单', adjustment: '登记结算调整' })[action.value] || '')
const page = useAdminPage(async valid => {
  const [listResult, rulesResult, totalsResult, peopleResult] = await Promise.allSettled([
    props.mode === 'rules' ? Promise.resolve({ items: [], total: 0 }) : settlementList<Reward | Statement | Adjustment | SettlementApplication>(kind.value, (pageNumber.value - 1) * 20, filters()),
    props.mode === 'rules' && props.user.is_super_admin ? rewardPolicy() : Promise.resolve(null),
    props.mode === 'rules' ? Promise.resolve(null) : settlementSummary(filters()),
    finance.value ? settlementAdmins() : Promise.resolve({ items: [] }),
  ])
  if (!valid()) return
  if (listResult.status === 'rejected') throw listResult.reason
  const list = listResult.value
  if (kind.value === 'rewards') rewards.value = list.items as Reward[]
  if (kind.value === 'statements') statements.value = list.items as Statement[]
  if (kind.value === 'adjustments') adjustments.value = list.items as Adjustment[]
  if (kind.value === 'requests') applications.value = list.items as SettlementApplication[]
  total.value = list.total
  const softErrors: string[] = []
  if (totalsResult.status === 'fulfilled') summary.value = totalsResult.value
  else if (props.mode !== 'rules') { summary.value = null; softErrors.push('结算汇总读取失败，列表仍可使用；请刷新重试') }
  if (peopleResult.status === 'fulfilled') accounts.value = peopleResult.value.items
  else if (finance.value) { accounts.value = []; softErrors.push('管理员列表读取失败，相关筛选暂不可用') }
  if (rulesResult.status === 'rejected') throw rulesResult.reason
  const rules = rulesResult.value
  if (rules && !policy.value) { policy.value = rules; reviewDays.value = rules.review_days == null ? '' : String(rules.review_days); payoutDays.value = rules.payout_days == null ? '' : String(rules.payout_days); cap.value = rules.max_reward_fen == null ? '' : (rules.max_reward_fen / 100).toFixed(2); enabled.value = rules.enabled; rate.value = (rules.rate_bps / 100).toFixed(2); holdDays.value = rules.hold_days; defaultChannelRate.value = rules.channel_rates ? (rules.channel_rates.wechat / 100).toFixed(2) : rules.channel_rate_bps == null ? '' : (rules.channel_rate_bps / 100).toFixed(2); androidRate.value = rules.channel_rates ? (rules.channel_rates.virtual_android / 100).toFixed(2) : ''; iosRate.value = rules.channel_rates ? (rules.channel_rates.virtual_ios / 100).toFixed(2) : ''; defaults.value = feeDrafts(rules.shared_fees) }
  page.error.value = softErrors.join('；')
  const last = Math.max(1, Math.ceil(total.value / 20)); if (pageNumber.value > last) pageNumber.value = last
}, () => { dialog.value = false; applyOpen.value = false })
const { busy, loading, error, notice } = page
const route = useAdminListRoute(props.routeTab ?? 'settlements', { section, mode: kind, page: pageNumber, admin, q, status, channel, start, end, basis: dateBasis, timing, dispute: requestedDispute }, page.load)
watch(kind, () => { selected.value = []; if (route.restoring) return; status.value = nextStatus ?? ''; nextStatus = null; if (kind.value !== 'requests') timing.value = ''; if (pageNumber.value !== 1) pageNumber.value = 1; else void page.load() })
watch(pageNumber, page.load)
watch([channelRate, fees, tax, evidence], () => { confirmed.value = false }, { deep: true })
function run(operation: () => Promise<unknown>, message: string) {
  void page.act(async valid => { await operation(); if (!valid()) return; dialog.value = false; selected.value = []; notice.value = message; requestRefresh.value++; await page.load() })
}
function savePolicy() {
  void page.act(async valid => {
    if (!policy.value) return
    const result = await saveRewardPolicy(props.user.id, { ...policy.value, enabled: enabled.value, max_reward_fen: cap.value.trim() ? moneyFen(cap.value) : null, rate_bps: percentageBps(rate.value), hold_days: Number(holdDays.value), review_days: processingDays(reviewDays.value), payout_days: processingDays(payoutDays.value), channel_rate_bps: percentageBps(defaultChannelRate.value), channel_rates: { wechat: percentageBps(defaultChannelRate.value), virtual_android: percentageBps(androidRate.value), virtual_ios: percentageBps(iosRate.value) }, shared_fees: sharedFeeValues(defaults.value), reason: policyReason.value })
    if (valid()) { policy.value = result; policyReason.value = ''; notice.value = '规则已保存：奖励规则用于新订单，处理目标用于新申请' }
  })
}
function open(actionName: string, item: Reward | Statement) {
  if (actionName === 'paid' && 'snapshot' in item) { navigateAdmin('financePayments', { statement: item.id }); return }
  reviewBlocked.value = true
  action.value = actionName; reward.value = 'order_id' in item ? item : null; statement.value = 'snapshot' in item ? item : null
  beneficiary.value = item.beneficiary; beneficiaryName.value = item.beneficiary_name
  const savedRate = reward.value?.costs ? reward.value.costs.channel_rate_bps : reward.value?.policy.channel_rate_bps
  channelRate.value = savedRate == null ? '' : (savedRate / 100).toFixed(2)
  fees.value = feeDrafts(actionName === 'costs' ? reward.value?.costs?.shared_fees || reward.value?.policy.shared_fees || [] : [])
  tax.value = ''; evidence.value = actionName === 'costs' ? reward.value?.costs?.evidence || '' : ''; confirmed.value = false
  amount.value = ''; reason.value = ''; differenceReason.value = ''; adjustmentRequest.value = crypto.randomUUID(); dialog.value = true
}
function submit() {
  run(async () => {
    if (action.value === 'costs' && reward.value) return confirmRewardCosts(props.user.id, reward.value, { channel_rate_bps: percentageBps(channelRate.value), shared_fees: sharedFeeValues(fees.value), evidence: evidence.value, confirmed: true })
    if (action.value === 'review' && statement.value) {
      if (reviewBlocked.value) throw new Error('请先完成审核前账单检查并处理差异')
      return approveStatement(props.user.id, statement.value, { personal_fees: personalFeeValues(fees.value), tax_fen: moneyFen(tax.value), evidence: evidence.value, confirmed: true, difference_reason: differenceReason.value })
    }
    if (action.value === 'void' && statement.value) return voidStatement(props.user.id, statement.value, reason.value)
    if (action.value === 'adjustment') return recordAdjustment(props.user.id, { beneficiary: beneficiary.value, amount_fen: moneyFen(amount.value, true), reason: reason.value, evidence: evidence.value, request_id: adjustmentRequest.value })
  }, '结算记录已更新')
}
const costInput = computed(() => {
  try { const rate = percentageBps(channelRate.value); return { channel: channelFeeFen(reward.value?.amount_fen ?? 0, rate), channelRate: rate, fees: sharedFeeValues(fees.value) } } catch { return null }
})
const reviewInput = computed(() => {
  try { return { fees: personalFeeValues(fees.value), tax: moneyFen(tax.value) } } catch { return null }
})
const example = computed(() => {
  try { const amount = moneyFen(exampleAmount.value), channelRate = percentageBps(exampleChannel.value === 'virtual_ios' ? iosRate.value : exampleChannel.value === 'virtual_android' ? androidRate.value : defaultChannelRate.value); return { amount, channel: channelFeeFen(amount, channelRate), channelRate, fees: sharedFeeValues(defaults.value), rate: percentageBps(rate.value), cap: cap.value.trim() ? moneyFen(cap.value) : null } } catch { return null }
})
const exampleReward = computed(() => example.value ? calculateReward(example.value.amount, example.value.channel, example.value.fees, example.value.rate, example.value.cap).commission : null)
function fillStarter() {
  const value = starterPolicy()
  rate.value = (value.rate_bps / 100).toFixed(2); holdDays.value = value.hold_days; defaultChannelRate.value = (value.channel_rate_bps / 100).toFixed(2); androidRate.value = (value.channel_rates.virtual_android / 100).toFixed(2); iosRate.value = (value.channel_rates.virtual_ios / 100).toFixed(2); defaults.value = feeDrafts(value.shared_fees)
  policyReason.value = '采用起步建议，待按业务成本调整'
  notice.value = '建议已填入，保存后生效；奖励启用状态未改变'
}
const preview = computed(() => {
  try {
    if (action.value === 'costs' && reward.value && costInput.value) return calculateReward(reward.value.amount_fen, costInput.value.channel, costInput.value.fees, reward.value.policy.rate_bps, reward.value.policy.max_reward_fen).commission
    if (action.value === 'review' && statement.value) return statement.value.gross_fen + statement.value.adjustment_fen - resolvePersonalFees(personalFeeValues(fees.value), statement.value.gross_fen, statement.value.adjustment_fen).reduce((n, fee) => n + fee.amount_fen, 0) - moneyFen(tax.value)
  } catch { /* 未填的费用不显示为零。 */ }
  return null
})
function create() { run(async () => { await createStatement(props.user.id, selected.value); kind.value = 'statements' }, '已生成结算草稿，请核对个人费用及税费') }
function createAdjustment(item: Adjustment) { run(async () => { await createStatement(props.user.id, [], item.beneficiary); kind.value = 'statements' }, '已合并该管理员全部待处理调整，请核对结算') }
function refresh() { selected.value = []; policy.value = null; void page.load() }
function select(id: string, value: boolean | 'indeterminate') { selected.value = value === true ? [...selected.value, id] : selected.value.filter(item => item !== id) }
function selectable(item: Reward) {
  return rewardApplicationState(item) === 'available' && (!finance.value || canCosts.value && !!item.costs)
}
function applyAll() { applyIds.value = []; applyAllEligible.value = true; applyOpen.value = true }
function apply() { applyAllEligible.value = false; applyIds.value = [...selected.value]; applyOpen.value = true }
function applied() { selected.value = []; applyOpen.value = false; kind.value = 'requests'; notice.value = '申请已提交，等待超级管理员对账审核'; void page.load() }
</script>

<template>
  <section class="admin-section promotion-workspace">
    <PromotionTabs v-if="sections.length > 1" :model-value="activeSection" id="settlements" label="结算页面导航" :items="sections" :disabled="busy || dialog || applyOpen" @update:model-value="section = $event" />
    <div v-if="finance" class="promotion-context-links"><UButton v-if="canPermission('financePayments:view')" label="前往付款管理" icon="i-lucide-credit-card" variant="link" @click="navigateAdmin('financePayments')" /><UButton v-if="canPermission('financeBills:view')" label="前往账单对账" icon="i-lucide-file-check-2" variant="link" @click="navigateAdmin('financeBills')" /><UButton v-if="canPermission('financeMonthly:view')" label="前往月度对账" icon="i-lucide-calendar-days" variant="link" @click="navigateAdmin('financeMonthly')" /></div>
    <UAlert v-if="error" :title="error" color="error" />
    <UAlert v-if="notice" :title="notice" color="success" />
    <section v-show="activeSection === 'workspace'" id="settlements-panel-workspace" role="tabpanel" aria-labelledby="settlements-tab-workspace" class="promotion-panel-stack">
      <div class="promotion-panel">
        <div class="promotion-heading settlement-heading"><div><h2>{{ finance ? '结算待办' : '我的推广收益' }}</h2><p>{{ finance ? '处理申请、核对费用并审核应付，审核后前往付款管理办理。' : '查看可申请奖励，跟进审核与付款进度。' }}</p></div></div>
        <SettlementOverview v-if="summary && finance" :summary="summary" :disabled="loading || busy" @select="selectScope" @timing="selectTiming" />
        <SettlementPromoterOverview v-else-if="summary" :summary="summary" :disabled="loading || busy" @select="selectScope" @timing="selectTiming" />
      </div>
      <div class="promotion-panel">
        <div class="settlement-list-tabs">
          <div aria-label="结算工作区导航"><UButton v-for="tab in [{ value: 'rewards', label: '首付奖励' }, { value: 'requests', label: '结算申请与处理' }, { value: 'statements', label: '结算单' }, { value: 'adjustments', label: '退款与历史调整' }]" :key="tab.value" :label="tab.label" variant="ghost" color="neutral" size="md" :aria-pressed="kind === tab.value" :disabled="busy || loading" @click="kind = tab.value as SettlementKind" /></div>
          <div><UButton label="刷新记录" icon="i-lucide-refresh-cw" color="neutral" variant="ghost" size="md" :loading="loading" :disabled="busy" @click="refresh" /><UButton v-permission="'settlements:export'" label="导出结算明细" icon="i-lucide-download" color="neutral" variant="outline" size="md" :disabled="busy || loading" @click="run(() => exportWorkbook(kind, filters()), 'Excel 结算明细已导出')" /></div>
        </div>
        <form class="promotion-filter" aria-label="结算记录筛选" @submit.prevent="search">
          <UInput v-model="q" icon="i-lucide-search" size="md" class="settlement-search" placeholder="搜索管理员、订单或结算编号" aria-label="搜索结算记录" maxlength="120" :disabled="loading || busy" />
          <USelect v-model="status" size="md" :items="stateOptions" aria-label="结算状态" :disabled="loading || busy" />
          <UButton label="筛选结算记录" icon="i-lucide-filter" size="md" type="submit" :loading="loading" :disabled="busy" />
          <UButton v-if="admin || q || status || channel || start || end || timing || dateBasis !== 'created'" label="清空筛选" icon="i-lucide-rotate-ccw" color="neutral" size="md" variant="ghost" :disabled="loading || busy" @click="resetFilters" />
          <details class="filter-more" :open="!!(admin || channel || start || end || timing || dateBasis !== 'created')"><summary>更多筛选{{ admin || channel || start || end || timing || dateBasis !== 'created' ? ' · 已设置' : '' }}</summary><div class="actions-row">
            <USelect v-if="finance" v-model="admin" :items="[{ value: '', label: '全部管理员' }, ...accounts.map(item => ({ value: String(item.id), label: item.username }))]" aria-label="结算管理员" :disabled="loading || busy" />
            <USelect v-model="channel" :items="[{ value: '', label: '全部支付渠道' }, { value: 'wechat', label: '普通微信支付' }, { value: 'virtual_android', label: '虚拟支付安卓等' }, { value: 'virtual_ios', label: '虚拟支付 iOS' }, { value: 'unknown', label: '渠道未知' }]" aria-label="结算支付渠道" :disabled="loading || busy" />
            <UFormField label="日期口径"><USelect v-model="dateBasis" :items="[{ value: 'created', label: '按记录创建日期' }, { value: 'paid', label: '按实际付款日期' }]" :disabled="loading || busy" @update:model-value="search" /></UFormField><UFormField v-if="kind === 'requests'" label="处理时效"><USelect v-model="timing" :items="[{ value: '', label: '全部处理时效' }, { value: 'stalled', label: '超过三天未更新' }, { value: 'review_overdue', label: '超过审核目标' }, { value: 'payout_overdue', label: '超过付款目标' }]" :disabled="loading || busy" @update:model-value="search" /></UFormField><UFormField :label="dateBasis === 'paid' ? '实际付款起始日期' : '记录创建起始日期'"><UInput v-model="start" type="date" :max="end || undefined" size="md" :disabled="loading || busy" /></UFormField><UFormField label="截止日期"><UInput v-model="end" type="date" :min="start || undefined" size="md" :disabled="loading || busy" /></UFormField>
          </div><p class="text-xs text-muted mt-3">{{ dateBasis === 'paid' ? '仅统计已留存实际付款时间的已付款记录，历史仅有登记时间的记录不纳入此口径。' : '汇总按各类记录创建日期计算。' }}管理员、关键词和渠道同步应用于汇总；状态与时效仅筛选当前列表，跨渠道结算单按整单金额显示。</p></details>
        </form>
        <div v-if="kind === 'rewards'" class="actions-row justify-between mb-4"><p class="text-xs text-muted">{{ finance ? '申请内订单到“结算申请与处理”对账；其他订单核对后可勾选生成结算草稿。' : canApply ? '满等待期即可申请，费用和最终应付以对账为准。' : '仅展示你的首付奖励；申请结算需开通相应权限。' }}</p><UButton v-if="!finance && canApply" label="预览全部可申请订单" :disabled="busy || loading" @click="applyAll" /></div>
        <p v-if="kind === 'requests'" class="text-xs text-muted mb-4">申请 → 对账核费 → 审核应付 → 付款登记</p>
        <div v-if="kind === 'rewards' && selected.length" class="selection-bar"><span class="text-sm">已选择 {{ selected.length }} 笔（包含其他分页） <UButton label="清空选择" variant="link" @click="selected = []" /></span><UButton v-if="canCosts" label="生成结算草稿" :disabled="busy" @click="create" /><UButton v-else-if="canApply && !finance" label="申请结算" :disabled="busy || loading" @click="apply" /></div>
    <div class="data-scroll">
      <table v-if="kind === 'rewards'" class="data-table"><thead><tr><th v-if="canSelect">选择</th><th>订单 / 推广管理员</th><th>实收 / 支付渠道</th><th>税前奖励</th><th>状态 / 可结算日期</th><th>操作</th></tr></thead><tbody>
        <tr v-for="item in rewardRows" :key="item.order_id">
          <td v-if="canSelect"><UCheckbox :model-value="selected.includes(item.order_id)" :aria-label="'选择订单' + item.order_id" :disabled="busy || loading || !selectable(item)" @update:model-value="select(item.order_id, $event)" /></td>
          <td class="record-identity">{{ item.beneficiary_name }}<div class="text-xs text-muted break-all">{{ item.order_id }}</div></td>
          <td><strong class="tabular-nums">{{ yuan(item.amount_fen) }}</strong><div class="text-xs">{{ channelLabel(item.payment_channel, item.device_platform) }}</div></td>
          <td>
            <strong class="tabular-nums">{{ item.costs ? '税前奖励' : '参考税前奖励' }}：{{ item.calculation.commission === null ? '待核对' : yuan(item.calculation.commission) }}</strong>
            <p class="text-xs text-muted">{{ item.costs ? '费用已核对' : '费用待核对' }}</p>
            <p class="text-xs text-muted" aria-label="本单扣费与奖励比例">渠道 <span>{{ item.calculation.channelRate == null ? '待核对' : item.calculation.channelRate / 100 + '%' }}</span> · 奖励 {{ item.calculation.rate / 100 }}%</p>
          </td>
          <td class="record-status"><PromotionStatus :status="rewardApplicationState(item)" :label="applicationEligibilityLabels[rewardApplicationState(item)]" /><div class="text-xs">{{ dateTime(item.available_at) }}</div><div v-if="item.refund_status" class="text-xs">退款：{{ item.refund_status }}</div><div v-if="item.eligibility_issue && rewardApplicationState(item) === 'exception'" class="text-xs">{{ item.eligibility_issue.reason }}<a v-if="canPermission('orders:view')" :href="'#orders?q=' + encodeURIComponent(item.eligibility_issue.order_id)" class="block text-primary">{{ item.eligibility_issue.code === 'refund' ? '查看退款订单' : item.eligibility_issue.code === 'earlier_order' ? '查看未完成订单' : '查看相关订单' }}</a></div><div v-else-if="rewardApplicationState(item) === 'exception'" class="text-xs">请刷新以查看具体阻塞原因。</div><div class="text-xs">{{ item.reason }}</div></td>
          <td><div class="promotion-row-actions"><UButton v-if="canCosts && item.status === 'pending' && !item.statement_id" label="核对费用" icon="i-lucide-list-checks" variant="soft" :disabled="busy || loading" @click="open('costs', item)" /><UButton label="计算明细" color="neutral" variant="outline" :disabled="busy" @click="open('reward_detail', item)" /><UButton v-if="!finance && canApply && item.beneficiary === 'admin:' + user.id" label="发起奖励异议" variant="link" @click="dispute('reward', item.order_id)" /><PromotionActions v-if="finance && user.is_super_admin" :disabled="busy" :items="[{ label: '记调整', icon: 'i-lucide-sliders-horizontal', onSelect: () => open('adjustment', item) }]" /></div></td>
        </tr>
      </tbody></table>
      <table v-else-if="kind === 'statements'" class="data-table"><thead><tr><th>管理员 / 结算单</th><th>奖励 / 历史调整</th><th>个人费用 / 个税</th><th>最终应付 / 状态</th><th>操作</th></tr></thead><tbody>
        <tr v-for="item in statements" :key="item.id"><td class="record-identity">{{ item.beneficiary_name }}<div class="text-xs text-muted break-all">{{ item.id }}</div></td><td>{{ yuan(item.gross_fen) }} / {{ yuan(item.adjustment_fen) }}</td><td>{{ item.review === null ? '待核对' : yuan(item.personal_fen) }} / {{ item.tax_fen === null ? '待核对' : yuan(item.tax_fen) }}</td><td><strong>{{ item.net_fen === null ? '待核对' : yuan(Math.max(0, item.net_fen)) }}</strong><div class="mt-2"><PromotionStatus :status="item.status" :label="settlementStates[item.status]" /></div><SettlementTarget :status="item.status" :terms="item.snapshot.service_terms" :submitted-at="item.created_at" :approved-at="item.approved_at" /><div v-if="item.net_fen !== null && item.net_fen < 0" class="text-xs">剩余扣回 {{ yuan(-item.net_fen) }} 结转下期</div></td><td>
          <div class="promotion-row-actions"><UButton label="明细" color="neutral" variant="outline" :disabled="busy" @click="open('detail', item)" />
          <UButton v-if="!finance && canApply && item.beneficiary === 'admin:' + user.id" label="发起结算异议" variant="link" @click="dispute('statement', item.id)" /><template v-if="finance"><UButton v-if="canReview && item.status === 'draft'" label="审核结算" icon="i-lucide-list-checks" variant="soft" :disabled="busy" @click="open('review', item)" /><UButton v-if="canPayout && item.status === 'approved'" label="办理付款" icon="i-lucide-wallet" variant="soft" :disabled="busy" @click="navigateAdmin('financePayments', { statement: item.id })" /><PromotionActions :disabled="busy" :items="[...(user.is_super_admin ? [{ label: '记调整', icon: 'i-lucide-sliders-horizontal', onSelect: () => open('adjustment', item) }] : []), ...(canReview && ['draft', 'approved'].includes(item.status) ? [{ label: '作废', icon: 'i-lucide-circle-x', color: 'error' as const, onSelect: () => open('void', item) }] : [])]" /></template></div>
        </td></tr>
      </tbody></table>
      <table v-else-if="kind === 'adjustments'" class="data-table"><thead><tr><th>管理员</th><th>调整金额</th><th>原因 / 凭据</th><th>状态</th></tr></thead><tbody><tr v-for="item in adjustments" :key="item.id"><td>{{ item.beneficiary_name }}</td><td>{{ yuan(item.amount_fen) }}</td><td>{{ item.reason }}<div class="text-xs whitespace-pre-wrap">{{ item.evidence }}</div></td><td>{{ item.statement_id ? '已入结算单' : '待下次结算抵扣或补付' }}<UButton v-if="finance && user.is_super_admin && !item.statement_id && item.amount_fen > 0" label="生成调整结算单" variant="link" :disabled="busy" @click="createAdjustment(item)" /></td></tr></tbody></table>
    </div>
    <SettlementRequests v-if="kind === 'requests'" :user="viewUser" :items="applications" :refresh-key="requestRefresh" @refresh="page.load" @statement="open" />
    <div v-if="!loading && !total" class="promotion-empty"><UIcon name="i-lucide-inbox" class="promotion-empty-icon" aria-hidden="true" /><strong>暂无结算记录</strong><p>{{ admin || q || status || channel || start || end || timing || dateBasis !== 'created' ? '当前条件没有匹配记录，可清空筛选重新查看。' : '奖励产生后，可在这里申请结算并跟进处理进度。' }}</p><UButton v-if="admin || q || status || channel || start || end || timing || dateBasis !== 'created'" label="查看全部结算记录" variant="outline" size="md" @click="resetFilters" /></div>
    <div class="table-footer"><span>共 {{ total }} 条</span><UPagination v-model:page="pageNumber" :total="total" :items-per-page="20" :disabled="loading || busy" /></div>
      </div>
    </section>
    <section v-if="activeSection === 'monthly'" id="settlements-panel-monthly" role="tabpanel" aria-labelledby="settlements-tab-monthly" class="promotion-panel"><SettlementMonthly :user="viewUser" /></section>
    <section v-if="activeSection === 'disputes'" id="settlements-panel-disputes" role="tabpanel" aria-labelledby="settlements-tab-disputes" class="promotion-panel"><SettlementDisputes :user="viewUser" :personal="!finance" :target="disputeTarget" :requested="requestedDispute" @updated="requestRefresh++" /></section>
    <section v-if="!finance && mode !== 'rules' && canApply" v-show="activeSection === 'payee'" id="settlements-panel-payee" role="tabpanel" aria-labelledby="settlements-tab-payee" class="promotion-panel promotion-settings"><div class="promotion-heading"><div><h2>收款资料</h2><p>管理用于推广结算的收款账户，已有结算单保留原收款快照。</p></div></div><SettlementPayee :actor="user.id" /></section>
    <section v-if="mode !== 'rules'" v-show="activeSection === 'notices'" id="settlements-panel-notices" role="tabpanel" aria-labelledby="settlements-tab-notices" class="promotion-panel"><div class="promotion-heading"><div><h2>结算提醒</h2><p>查看申请审核、付款与异常处理的最新进度。</p></div></div><SettlementNotices :personal="!finance" @dispute="requestedDispute = $event; disputeTarget = null; section = 'disputes'" :actor="user.id" :refresh-key="requestRefresh" @unread="unreadNotices = $event" @select="(next, word) => selectScope(next, '', word)" /></section>
    <section v-if="activeSection === 'rules'" id="settlements-panel-rules" role="tabpanel" aria-labelledby="settlements-tab-rules" class="promotion-panel promotion-settings">
      <div class="promotion-heading"><div><h2>奖励与结算规则</h2><p>{{ mode === 'rules' && user.is_super_admin ? '维护新订单奖励、渠道费率和新申请处理目标。' : '推广前了解奖励资格、扣费方式和处理时效。' }}</p></div></div>
      <ReferralRules v-if="!user.is_super_admin || mode === 'personal'" :area="mode === 'rules' ? 'referrals' : 'settlements'" expanded />
    <div v-if="mode === 'rules' && user.is_super_admin && policy">
      <h3 class="font-semibold">奖励规则 · {{ policy.enabled ? '已启用' : '未启用' }} · {{ (policy.rate_bps / 100).toFixed(2) }}%</h3>
      <form class="field-stack mt-4" @submit.prevent="savePolicy">
        <p class="text-sm">起步建议：首付奖励 10%，等待 14 天；普通微信费率参考 0.6%，虚拟支付安卓/鸿蒙/Windows 参考 1%，iOS 参考 12%（含 Apple 佣金，不重复扣）；以实际类目合同和账单为准；服务成本分摊先设为 0%，个人费用无实际发生则为 0。可按实际约定调整，不代表行业统一标准。</p>
        <UButton label="填入起步建议" variant="outline" :disabled="busy" class="self-start" @click="fillStarter" />
        <UCheckbox v-model="enabled" label="启用首次付费奖励" :disabled="busy" />
        <fieldset class="settings-block"><legend>首付奖励</legend><div class="settings-fields">
          <UFormField label="每单奖励上限（元，留空不限）"><UInput v-model="cap" inputmode="decimal" :disabled="busy" /></UFormField>
          <UFormField label="奖励比例（%）" required><UInput v-model="rate" inputmode="decimal" required :disabled="busy" /></UFormField>
          <UFormField label="付款后等待天数" required><UInput v-model="holdDays" type="number" min="0" max="365" step="1" required :disabled="busy" /></UFormField>
        </div></fieldset>
        <fieldset class="settings-block"><legend>支付渠道费率</legend><div class="settings-fields">
          <UFormField label="普通微信支付费率（%）" required><UInput v-model="defaultChannelRate" inputmode="decimal" required :disabled="busy" /></UFormField>
          <UFormField label="虚拟支付安卓/鸿蒙/Windows费率（%）" required><UInput v-model="androidRate" inputmode="decimal" required :disabled="busy" /></UFormField>
          <UFormField label="虚拟支付iOS费率（%）" required><UInput v-model="iosRate" inputmode="decimal" required :disabled="busy" /></UFormField>
        </div></fieldset>
        <fieldset class="settings-block"><legend>审核与付款时效</legend><div class="settings-fields">
          <UFormField label="审核处理目标（自然日，留空不指定）"><UInput v-model="reviewDays" type="number" min="1" max="90" step="1" :disabled="busy" /></UFormField>
          <UFormField label="付款处理目标（自然日，留空不指定）"><UInput v-model="payoutDays" type="number" min="1" max="90" step="1" :disabled="busy" /></UFormField>
        </div></fieldset>
        <p class="text-xs text-muted">审核从提交申请起算，付款从审核通过起算；保存后新申请留存这组目标，已有申请保持提交时的约定。未配置时不展示预计时间。</p>
        <SettlementFees v-model="defaults" label="默认共同费用" allow-percent :disabled="busy" />
        <p class="text-xs text-muted">默认费用用于填写提示，每单仍需按约定或成本凭据核对。渠道费率按实际支付渠道合同逐单核对，个人费用在结算单中填写。首次启用不补发历史订单奖励。</p>
        <details class="rounded border border-default p-4">
          <summary class="cursor-pointer font-medium">规则试算（不入账）</summary>
          <div class="actions-row my-3">
            <UFormField label="试算支付渠道"><USelect v-model="exampleChannel" :items="[{ value: 'wechat', label: '普通微信支付' }, { value: 'virtual_android', label: '虚拟支付安卓/鸿蒙/Windows' }, { value: 'virtual_ios', label: '虚拟支付iOS' }]" /></UFormField>
            <UFormField label="试算实收（元）"><UInput v-model="exampleAmount" inputmode="decimal" /></UFormField>
          </div>
          <p class="text-xs text-muted mb-3">试算采用所选渠道对应的费率；建议值按当前非短剧/小说类目主动购买口径提供，需按你的类目和渠道合同核实。优惠费率可能变化，保存只影响新订单。个人费用和个税暂按 0 演示；实际结款需分别核对。</p>
          <template v-if="example && exampleReward !== null">
            <RewardCalculation v-bind="example" />
            <SettlementCalculation class="mt-3" :gross="exampleReward" :adjustment="0" :fees="[]" :tax="0" />
          </template>
          <p v-else class="text-sm">请填写有效的金额、比例和费用名称以查看试算。</p>
        </details>
        <UFormField label="规则变更说明" required><UInput v-model="policyReason" minlength="2" maxlength="500" required :disabled="busy" class="w-full" /></UFormField>
        <div class="promotion-form-footer"><span>保存后应用于新订单和新申请</span><UButton label="保存奖励规则" icon="i-lucide-check" size="md" type="submit" :loading="busy" /></div>
      </form>
    </div>
    </section>
    <SettlementApplyDialog v-if="applyOpen" :actor="user.id" :order-ids="applyIds" :all-eligible="applyAllEligible" @close="applyOpen = false" @saved="applied" />
    <UModal v-model:open="dialog" :title="title" :dismissible="!busy"><template #body>
      <UAlert v-if="error" :title="error" color="error" class="mb-4" />
      <div v-if="action === 'reward_detail' && reward" class="field-stack text-sm">
        <p>{{ reward.beneficiary_name }} · 订单 {{ reward.order_id }}</p>
        <RewardCalculation v-if="rewardDetail" v-bind="rewardDetail" />
        <p v-if="reward.costs" class="whitespace-pre-wrap">核对依据：{{ reward.costs.evidence }}</p>
        <p>最终到手金额以包含本笔订单的结算单为准。</p>
      </div>
      <div v-else-if="action === 'detail' && statement" class="field-stack text-sm">
        <SettlementEvidence :actor="user.id" :item="statement" :finance="finance" :payee-access="canPayout" :file-access="canCosts || canReview || canPayout" @updated="statement = $event" />
        <p>{{ statement.beneficiary_name }} · {{ settlementStates[statement.status] }}</p>
        <SettlementTarget :status="statement.status" :terms="statement.snapshot.service_terms" :submitted-at="statement.created_at" :approved-at="statement.approved_at" />
        <SettlementChannels v-if="statement.snapshot.channels?.length" :channels="statement.snapshot.channels" />
        <div v-for="item in statement.snapshot.items" :key="item.order_id" class="border-b border-default pb-3"><p class="break-all">订单 {{ item.order_id }} · {{ channelLabel(item.payment_channel, item.device_platform) }}</p><RewardCalculation :amount="item.amount_fen" :channel="item.costs.channel_fee_fen" :channel-rate="item.costs.channel_rate_bps" :fees="item.costs.shared_fees" :rate="item.policy.rate_bps" :cap="item.policy.max_reward_fen" :commission="item.commission_fen" /><p class="whitespace-pre-wrap">核对凭据：{{ item.costs.evidence }}</p></div>
        <p v-for="item in statement.snapshot.adjustments" :key="item.id">历史调整 {{ yuan(item.amount_fen) }} · {{ item.reason }}</p>
        <p>税前奖励合计：{{ statement.snapshot.items.map(item => yuan(item.commission_fen)).join(' + ') || yuan(0) }} = {{ yuan(statement.gross_fen) }}</p>
        <SettlementCalculation :gross="statement.gross_fen" :adjustment="statement.adjustment_fen" :fees="statement.review?.personal_fees ?? null" :tax="statement.tax_fen" :net="statement.net_fen" />
        <p v-if="statement.review" class="whitespace-pre-wrap">核对依据：{{ statement.review.evidence }}</p>
        <p>最终应付：{{ statement.net_fen === null ? '待核对' : yuan(Math.max(0, statement.net_fen)) }}</p><p v-if="statement.receipt" class="break-all">付款凭证：{{ statement.receipt }}</p><p v-if="statement.reason">作废原因：{{ statement.reason }}</p>
      </div>
      <form v-else class="field-stack" @submit.prevent="submit">
        <p>{{ beneficiaryName }}</p>
        <template v-if="action === 'costs' && reward">
          <p>订单实收 {{ yuan(reward.amount_fen) }} · 奖励比例 {{ reward.policy.rate_bps / 100 }}%</p>
          <UFormField label="实际支付渠道手续费率（%）" required><UInput v-model="channelRate" inputmode="decimal" required :disabled="busy" /></UFormField>
          <SettlementFees v-model="fees" label="共同费用" references allow-percent :disabled="busy" />
          <p class="text-xs text-muted">按本单支付渠道合同核对费率，渠道费由实收乘费率自动计算，四舍五入到分。旧记录未保存费率时需重新填写；共同费用中不要再次计入渠道费。</p>
          <RewardCalculation :amount="reward.amount_fen" :channel="costInput?.channel ?? null" :channel-rate="costInput?.channelRate" :fees="costInput?.fees ?? null" :rate="reward.policy.rate_bps" />
        </template>
        <template v-if="action === 'review' && statement">
          <SettlementEvidence :actor="user.id" :item="statement" :finance="true" :payee-access="canPayout" :file-access="canReview" purpose="review" @updated="statement = $event" @busy="evidenceBusy = $event" @blocked="value => { reviewBlocked = value; if (value) confirmed = false }" />
          <UFormField label="与申请参考金额不同的原因（有差异时必填）"><UTextarea v-model="differenceReason" maxlength="1000" :disabled="busy" /></UFormField>
          <p>税前奖励 {{ yuan(statement.gross_fen) }}，历史调整 {{ yuan(statement.adjustment_fen) }}</p>
          <SettlementFees v-model="fees" label="个人费用" references allow-percent personal :disabled="busy" />
          <UFormField label="实际代扣个人所得税（元）" required><UInput v-model="tax" inputmode="decimal" required :disabled="busy" /></UFormField>
          <p class="text-xs text-muted">个税按适用税务口径核定后填写，零税额也需填写依据。同一费用不能同时计入共同费用和个人费用。</p>
          <SettlementCalculation :gross="statement.gross_fen" :adjustment="statement.adjustment_fen" :fees="reviewInput?.fees ?? null" :tax="reviewInput?.tax ?? null" />
        </template>
        <template v-if="['costs', 'review', 'adjustment'].includes(action)">
          <UFormField label="核对依据 / 凭据编号" required><UTextarea v-model="evidence" minlength="2" maxlength="1000" required :disabled="busy" class="w-full" /></UFormField>
        </template>
        <template v-if="['costs', 'review'].includes(action)">
          <p class="font-semibold">{{ action === 'costs' ? '税前奖励' : '最终应付' }}：{{ preview === null ? '待填写' : yuan(Math.max(0, preview)) }}</p>
          <p v-if="preview !== null && preview < 0" class="text-sm">未抵扣完 {{ yuan(-preview) }}，结转下期</p>
          <UCheckbox v-model="confirmed" label="已据实核对全部费用及凭据，无重复扣费" :disabled="busy" />
        </template>
        <template v-if="action === 'adjustment'"><p class="text-xs text-muted">正数补付，负数扣回。新调整会作废此管理员未付款的结算单，需要重新生成并审核。已扣个税的退回只能根据实际退税凭证补记。</p><UFormField label="调整金额（元，可为负数）" required><UInput v-model="amount" inputmode="decimal" required :disabled="busy" /></UFormField></template>
        <UFormField v-if="['void', 'adjustment'].includes(action)" label="原因" required><UTextarea v-model="reason" minlength="2" maxlength="500" required :disabled="busy" class="w-full" /></UFormField>
        <UButton :label="action === 'review' ? '核对并批准结算' : '确认保存'" size="md" :color="action === 'void' ? 'error' : 'primary'" type="submit" :loading="busy" :disabled="busy || evidenceBusy || action === 'review' && reviewBlocked || ['costs', 'review'].includes(action) && !confirmed" />
      </form>
    </template></UModal>
  </section>
</template>
