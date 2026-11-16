<script setup lang="ts">
import { computed, nextTick, onDeactivated, onUnmounted, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { dateTime, yuan } from '../growth'
import { canPermission } from '../permissions'
import { applicationDetail, applicationStates, closeApplication, createStatement, startApplication, type ApplicationDetail, type Reward, type SettlementApplication, type Statement } from '../settlements'
import SettlementApplicationSummary from './SettlementApplicationSummary.vue'
import SettlementCalculation from './SettlementCalculation.vue'
import SettlementChannels from './SettlementChannels.vue'
import SettlementOrderReview from './SettlementOrderReview.vue'
import SettlementDifference from './SettlementDifference.vue'
import SettlementTimeline from './SettlementTimeline.vue'
import SettlementRecovery from './SettlementRecovery.vue'
import SettlementEvidence from './SettlementEvidence.vue'
import SettlementTarget from './SettlementTarget.vue'
import PromotionStatus from './PromotionStatus.vue'
import { financeGrant, financeUser } from '../promotion-finance'

const props = defineProps<{ user: UserInfo; items: SettlementApplication[]; refreshKey?: number }>()
const finance = computed(() => financeUser(props.user)), canCosts = computed(() => financeGrant(props.user, 'Costs'))
function canProceed(item: SettlementApplication) {
  return item.status === 'approved' ? financeGrant(props.user, 'Payout') : item.statement_id ? financeGrant(props.user, 'Review') : canCosts.value
}
const emit = defineEmits<{ refresh: []; costs: [item: Reward]; statement: [action: string, item: Statement] }>()
const open = ref(false), loading = ref(false), busy = ref(false), error = ref(''), reason = ref('')
const detail = ref<ApplicationDetail | null>(null), panel = ref<HTMLElement | null>(null), orderBusy = ref(false)
const locked = computed(() => busy.value || orderBusy.value || loading.value)
const stage = computed(() => detail.value?.request.status === 'paid' ? 4 : detail.value?.statement?.status === 'approved' ? 3 : detail.value?.statement?.status === 'draft' ? 2 : detail.value?.request.status === 'reviewing' ? 1 : 0)
watch(() => props.refreshKey, () => { if (open.value && detail.value) void show(detail.value.request.id, false) })
function updated(value: ApplicationDetail) { detail.value = value; emit('refresh') }
function nextLabel(item: SettlementApplication) {
  if (item.status === 'pending') return '开始对账'
  if (item.status === 'approved') return '办理付款'
  if (item.status === 'reviewing') return item.statement_summary?.status === 'draft' || item.statement_id ? '审核费用与税费' : '继续对账'
  return ['invalidated', 'rejected', 'cancelled'].includes(item.status) ? '处理异常申请' : '查看结算结果'
}
async function proceed(item: SettlementApplication) {
  await show(item.id)
  if (!detail.value || detail.value.request.id !== item.id) return
  if (detail.value.request.status === 'pending') start()
  else if (detail.value.statement?.status === 'draft') statement('review')
  else if (detail.value.statement?.status === 'approved') statement('paid')
}

let sequence = 0
let returnFocus: HTMLElement | null = null
function closePanel() { open.value = false; returnFocus?.focus({ preventScroll: true }) }
onUnmounted(() => { sequence++ })
onDeactivated(() => { sequence++; open.value = false; busy.value = false; loading.value = false; detail.value = null })
async function show(id: string, scroll = true) {
  if (locked.value) return
  const token = ++sequence
  if (scroll) returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  open.value = true; loading.value = true; detail.value = null; error.value = ''; reason.value = ''
  try { const value = await applicationDetail(id); if (sequence === token) detail.value = value }
  catch (e) { if (sequence === token) error.value = e instanceof Error ? e.message : '读取申请失败' }
  finally { if (sequence === token) { loading.value = false; if (scroll) { await nextTick(); panel.value?.focus({ preventScroll: true }); panel.value?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }) } } }
}
async function act(operation: () => Promise<unknown>) {
  if (busy.value || !detail.value) return
  const id = detail.value.request.id, token = sequence
  busy.value = true; error.value = ''
  try {
    await operation()
    if (sequence !== token) return
    const value = await applicationDetail(id)
    if (sequence === token) { detail.value = value; emit('refresh') }
  } catch (e) { if (sequence === token) error.value = e instanceof Error ? e.message : '操作失败，请刷新重试' }
  finally { if (sequence === token) busy.value = false }
}
function start() { if (detail.value) void act(() => startApplication(props.user.id, detail.value!.request)) }
function create() {
  if (detail.value) void act(() => createStatement(props.user.id, [], undefined, detail.value!.request.id))
}
function close(cancel: boolean) {
  if (detail.value) void act(() => closeApplication(props.user.id, detail.value!.request, reason.value, cancel))
}
async function recovered(id: string) { emit('refresh'); await show(id) }
function statement(action: string) { if (detail.value?.statement) { emit('statement', action, detail.value.statement) } }
</script>

<template>
  <div class="data-scroll"><table class="data-table"><thead><tr><th>申请人 / 申请编号</th><th>奖励 / 最终应付</th><th>处理进度 / 申请时间</th><th>说明 / 操作</th></tr></thead><tbody>
    <tr v-for="item in items" :key="item.id" :class="{ 'promotion-selected-row': open && detail?.request.id === item.id }">
      <td class="record-identity"><strong>{{ item.beneficiary_name }}</strong><div class="text-xs text-muted break-all">{{ item.id }}</div></td>
      <td>参考税前 {{ item.snapshot.reference_gross_fen === null ? '待核对' : yuan(item.snapshot.reference_gross_fen) }}<div v-if="item.snapshot.unknown_orders" class="text-xs">{{ item.snapshot.unknown_orders }} 笔渠道费率待核对</div><div v-if="item.statement_summary">最终应付：{{ item.statement_summary.net_fen == null ? '待审核' : yuan(Math.max(0, item.statement_summary.net_fen)) }}</div><div class="text-xs text-muted">{{ item.snapshot.items.length }} 笔订单 · 以对账结果为准</div></td>
      <td class="record-status"><PromotionStatus :status="item.status" :label="applicationStates[item.status]" /><div v-if="['pending', 'reviewing'].includes(item.status)" class="text-xs">订单核对 {{ item.confirmed_orders ?? 0 }} / {{ item.snapshot.items.length }} 笔{{ item.statement_id ? ' · 已生成结算单' : '' }}</div><div class="text-xs">{{ dateTime(item.created_at) }}</div><SettlementTarget :status="item.status" :terms="item.snapshot.service_terms" :submitted-at="item.created_at" :approved-at="item.statement_summary?.approved_at" /></td>
      <td class="record-status"><p v-if="item.reason || item.note" class="text-xs text-muted mb-2 whitespace-pre-wrap">{{ item.reason || item.note }}</p><div class="promotion-row-actions"><UButton v-if="canProceed(item) && ['pending', 'reviewing', 'approved'].includes(item.status)" :label="nextLabel(item)" trailing-icon="i-lucide-arrow-right" variant="soft" :disabled="locked" @click="proceed(item)" /><UButton label="申请明细" icon="i-lucide-file-text" color="neutral" variant="outline" :disabled="locked" @click="show(item.id)" /></div></td>
    </tr>
  </tbody></table></div>
  <section v-if="open" ref="panel" tabindex="-1" class="promotion-detail-panel space-y-4 scroll-mt-4" aria-label="结算处理区">
    <div class="actions-row justify-between"><h3 class="font-semibold">{{ finance ? '结算处理' : '申请进度与结果' }}</h3><UButton label="收起处理区" icon="i-lucide-arrow-up" color="neutral" variant="outline" :disabled="locked" @click="closePanel" /></div>
    <ol v-if="detail" class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm" aria-label="结算进度">
      <li v-for="(label, index) in ['订单对账', '审核个人费用与税费', '付款登记', '已结算']" :key="label" class="rounded p-3" :class="index < stage ? 'bg-primary/10 text-primary' : 'bg-elevated'">{{ index + 1 }}. {{ label }}</li>
    </ol>
    <UAlert v-if="error" :title="error" color="error" class="mb-3" />
    <p v-if="loading" role="status">正在读取申请…</p>
    <div v-else-if="detail" class="field-stack text-sm">
      <p>{{ detail.request.beneficiary_name }} · {{ applicationStates[detail.request.status] }}</p>
      <SettlementTarget :status="detail.request.status" :terms="detail.request.snapshot.service_terms" :submitted-at="detail.request.created_at" :approved-at="detail.statement?.approved_at" />
      <p v-if="detail.request.note">申请备注：{{ detail.request.note }}</p>
      <p v-if="detail.request.reason">处理说明：{{ detail.request.reason }}</p>
      <details class="border border-default rounded p-3" :open="!finance && !detail.statement"><summary class="cursor-pointer font-medium">提交时的奖励与扣费明细（留档）</summary><SettlementApplicationSummary class="mt-3" :snapshot="detail.request.snapshot" /></details>
      <SettlementDifference v-if="detail.difference" :value="detail.difference" />
      <p v-if="detail.request.snapshot.source_request_id" class="text-xs break-all">由原申请恢复：{{ detail.request.snapshot.source_request_id }}</p>
      <SettlementRecovery v-if="canPermission('settlements:create') && ['invalidated','rejected','cancelled'].includes(detail.request.status)" :key="detail.request.id" :actor="user.id" :item="detail.request" @busy="orderBusy = $event" @recovered="recovered" />
      <template v-if="detail.statement">
        <p class="font-medium">{{ detail.statement.status === 'void' ? '已作废的对账结果，请重新申请' : '当前对账结果' }}</p>
        <SettlementChannels v-if="detail.statement.snapshot.channels?.length" :channels="detail.statement.snapshot.channels" />
        <SettlementCalculation :gross="detail.statement.gross_fen" :adjustment="detail.statement.adjustment_fen" :fees="detail.statement.review?.personal_fees ?? null" :tax="detail.statement.tax_fen" :net="detail.statement.net_fen" />
        <SettlementEvidence :actor="user.id" :item="detail.statement" :finance="finance" :payee-access="financeGrant(user, 'Payout')" :file-access="canCosts || financeGrant(user, 'Review') || financeGrant(user, 'Payout')" @busy="orderBusy = $event" @updated="detail.statement = $event; emit('refresh')" />
        <p v-if="detail.statement.receipt" class="break-all">付款凭证：{{ detail.statement.receipt }}</p>
        <UButton label="查看完整结算明细" variant="outline" :disabled="locked" @click="statement('detail')" />
        <UButton v-if="financeGrant(user, 'Review') && detail.statement.status === 'draft'" label="审核个人费用与税费" :disabled="locked" @click="statement('review')" />
        <UButton v-if="financeGrant(user, 'Payout') && detail.statement.status === 'approved'" label="办理付款" :disabled="locked" @click="statement('paid')" />
      </template>
      <template v-if="canCosts && ['pending', 'reviewing'].includes(detail.request.status)">
        <UButton v-if="detail.request.status === 'pending'" label="开始对账" :loading="busy" @click="start" />
        <template v-if="detail.request.status === 'reviewing' && !detail.statement">
          <SettlementOrderReview :key="detail.request.id" :actor="user.id" :detail="detail" @updated="updated" @busy="orderBusy = $event" />
          <UButton label="生成本次申请结算单" :loading="busy" :disabled="locked || !detail.rewards.length || detail.rewards.some(item => !item.costs)" @click="create" />
        </template>
        <UFormField label="退回原因" required><UTextarea v-model="reason" minlength="2" maxlength="500" :disabled="locked" class="w-full" /></UFormField>
        <UButton label="退回申请" color="error" variant="outline" :disabled="locked || reason.trim().length < 2" @click="close(false)" />
      </template>
      <SettlementTimeline :items="detail.timeline ?? []" />
      <template v-if="detail.request.beneficiary === 'admin:' + user.id && detail.request.status === 'pending' && canPermission('settlements:create')">
        <UFormField label="撤回原因" required><UTextarea v-model="reason" minlength="2" maxlength="500" :disabled="locked" class="w-full" /></UFormField>
        <UButton label="撤回申请" variant="outline" :disabled="locked || reason.trim().length < 2" @click="close(true)" />
      </template>
    </div>
  </section>
</template>
