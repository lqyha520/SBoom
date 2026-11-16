<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { yuan } from '../growth'
import { applicationDetail, calculateReward, channelFeeFen, channelLabel, confirmApplicationCosts, feeDrafts, percentageBps, rewardCalculation, sharedFeeValues, type ApplicationDetail, type FeeDraft, type Reward } from '../settlements'
import RewardCalculation from './RewardCalculation.vue'
import SettlementFees from './SettlementFees.vue'

const props = defineProps<{ actor: number; detail: ApplicationDetail }>()
const emit = defineEmits<{ updated: [detail: ApplicationDetail]; busy: [value: boolean] }>()
const selected = ref(''), channelRate = ref(''), fees = ref<FeeDraft[]>([]), evidence = ref(''), confirmed = ref(false)
const busy = ref(false), error = ref(''), notice = ref(''), batch = ref(false), page = ref(1)
const initial = ref(''), useBill = ref(false)
const draftValue = () => JSON.stringify({ channelRate: channelRate.value, fees: fees.value })
const dirty = computed(() => !!evidence.value || confirmed.value || draftValue() !== initial.value)
watch(fees, () => { confirmed.value = false }, { deep: true })
let alive = true
onBeforeUnmount(() => { alive = false })
const remaining = computed(() => props.detail.rewards.filter(item => !item.costs))
const current = computed(() => props.detail.rewards.find(item => item.order_id === selected.value))
const currentBill = computed(() => props.detail.bill_checks?.find(item => item.order_id === selected.value))
const batchConflicts = computed(() => remaining.value.filter(item => { const check = props.detail.bill_checks?.find(row => row.order_id === item.order_id); return check && (check.differences.length > 0 || check.wechat_reconciliation?.differences.length || check.bill_row_id && check.channel_fee_fen !== rewardCalculation(item).channel) }).length)
const rows = computed(() => props.detail.rewards.slice((page.value - 1) * 20, page.value * 20))
const input = computed(() => {
  if (!current.value) return null
  try { const rate = useBill.value ? undefined : percentageBps(channelRate.value); if (useBill.value && !currentBill.value?.can_adopt) return null; return { channel: useBill.value ? currentBill.value!.channel_fee_fen! : channelFeeFen(current.value.amount_fen, rate!), channelRate: rate, fees: sharedFeeValues(fees.value) } }
  catch { return null }
})
const batchItems = computed(() => remaining.value.map(item => ({ item, calculation: rewardCalculation(item) })))
const batchUnknown = computed(() => batchItems.value.filter(row => row.calculation.channelRate === null).length)
const batchTotal = computed(() => batchItems.value.reduce((sum, row) => sum + (row.calculation.commission ?? 0), 0))
function choose(item: Reward | undefined) {
  useBill.value = false; selected.value = item?.order_id ?? ''; batch.value = false; confirmed.value = false; evidence.value = ''; error.value = ''
  const rate = item?.costs ? item.costs.channel_rate_bps : item?.policy.channel_rate_bps
  channelRate.value = rate == null ? '' : (rate / 100).toFixed(2)
  fees.value = feeDrafts(item?.costs?.shared_fees ?? item?.policy.shared_fees ?? [])
  initial.value = draftValue()
}
watch(() => props.detail.request.id, () => { choose(remaining.value[0]); page.value = 1; notice.value = '' }, { immediate: true })
function edit(item: Reward) {
  if (dirty.value && !window.confirm('切换订单会放弃尚未保存的核对内容，是否继续？')) return
  choose(item)
}
function openBatch() {
  if (dirty.value && !window.confirm('进入批量核对会放弃尚未保存的本笔内容，是否继续？')) return
  batch.value = true; confirmed.value = false; evidence.value = ''; error.value = ''
}
async function save() {
  if (busy.value || !confirmed.value || evidence.value.trim().length < 2) return
  if (batch.value && (!remaining.value.length || batchUnknown.value || batchConflicts.value) || !batch.value && (!current.value || !input.value)) return
  busy.value = true; emit('busy', true); error.value = ''; notice.value = ''
  const oldId = selected.value, wasBatch = batch.value
  try {
    const items = wasBatch ? batchItems.value.map(({ item, calculation }) => ({ order_id: item.order_id, revision: item.revision,
      channel_rate_bps: calculation.channelRate!, shared_fees: sharedFeeValues(feeDrafts(item.policy.shared_fees)), evidence: evidence.value, confirmed: true as const }))
      : [{ order_id: current.value!.order_id, revision: current.value!.revision, ...(useBill.value ? { bill_row_id: currentBill.value!.bill_row_id!, channel_fee_fen: input.value!.channel } : { channel_rate_bps: input.value!.channelRate }),
        shared_fees: input.value!.fees, evidence: evidence.value, confirmed: true as const }]
    await confirmApplicationCosts(props.actor, props.detail.request, items)
    if (!alive) return
    // 已保存后先清空确认，防止随后读取失败时拿旧版本重复保存。
    confirmed.value = false; evidence.value = ''
    const value = await applicationDetail(props.detail.request.id)
    if (!alive) return
    emit('updated', value)
    const next = value.rewards.find(item => !item.costs && item.order_id !== oldId)
    choose(next)
    if (next) page.value = Math.floor(value.rewards.indexOf(next) / 20) + 1
    notice.value = next ? '本笔已保存，已打开下一笔待核对订单' : '本次申请的订单费用已全部核对，可直接生成结算单'
  } catch (cause) {
    if (alive) { error.value = cause instanceof Error ? cause.message : '核对失败'; confirmed.value = false }
  } finally { if (alive) { busy.value = false; emit('busy', false) } }
}
async function refresh() {
  if (busy.value) return
  busy.value = true; emit('busy', true)
  try { const value = await applicationDetail(props.detail.request.id); if (alive) { emit('updated', value); choose(value.rewards.find(item => !item.costs)) } }
  catch (cause) { if (alive) error.value = cause instanceof Error ? cause.message : '刷新失败' }
  finally { if (alive) { busy.value = false; emit('busy', false) } }
}
</script>

<template>
  <section class="space-y-4" aria-label="连续核对订单费用">
    <div class="actions-row">
      <p class="font-semibold">订单费用：已核对 {{ detail.rewards.length - remaining.length }} / {{ detail.rewards.length }} 笔</p>
      <UButton v-if="remaining.length" label="按各单规则批量核对" variant="outline" :disabled="busy" @click="openBatch" />
      <UButton label="刷新核对进度" variant="outline" :disabled="busy" @click="refresh" />
    </div>
    <UAlert v-if="error" :title="error" color="error" />
    <UAlert v-if="notice" :title="notice" color="success" />
    <div class="data-scroll">
      <table class="data-table"><thead><tr><th>订单 / 渠道</th><th>实收 / 渠道费率</th><th>状态 / 奖励</th><th>操作</th></tr></thead><tbody>
        <tr v-for="item in rows" :key="item.order_id" :class="{ 'bg-primary/10': item.order_id === selected && !batch }">
          <td><span class="break-all">{{ item.order_id }}</span><div class="text-xs">{{ channelLabel(item.payment_channel, item.device_platform) }}</div></td>
          <td>{{ yuan(item.amount_fen) }} / {{ rewardCalculation(item).channelRate === null ? '费率待核对' : rewardCalculation(item).channelRate! / 100 + '%' }}</td>
          <td>{{ item.costs ? '已核对 · ' + yuan(item.commission_fen ?? 0) : '待核对' }}</td>
          <td><UButton :label="item.costs ? '修改费用' : '核对费用'" variant="link" :disabled="busy" @click="edit(item)" /></td>
        </tr>
      </tbody></table>
    </div>
    <UPagination v-if="detail.rewards.length > 20" v-model:page="page" :total="detail.rewards.length" :items-per-page="20" :disabled="busy" />
    <form v-if="batch || current" class="field-stack rounded border border-default p-4" @submit.prevent="save">
      <template v-if="batch">
        <p class="font-semibold">批量核对剩余 {{ remaining.length }} 笔订单</p>
        <p class="text-sm">每笔使用其下单时的渠道费率和共同费用规则，安卓与 iOS 分别计算；已核对订单保持原结果。请与实际账单核实后确认。</p>
        <p v-if="batchConflicts" role="alert">{{ batchConflicts }} 笔账单存在差异，请先逐笔处理，不能直接批量按规则确认。</p>
        <p v-if="batchUnknown" role="alert">{{ batchUnknown }} 笔缺少渠道费率，请先逐笔补充核对，不能将未知费用按零提交。</p>
        <details><summary class="cursor-pointer">展开本次批量扣费明细（{{ remaining.length }} 笔）</summary>
          <div v-for="row in batchItems" :key="row.item.order_id" class="mt-3"><p class="break-all">{{ row.item.order_id }} · {{ channelLabel(row.item.payment_channel, row.item.device_platform) }}</p><RewardCalculation v-bind="row.calculation" /></div>
        </details>
        <p class="font-semibold">本批参考税前奖励：{{ batchUnknown ? '待补充费率' : yuan(batchTotal) }}</p>
      </template>
      <template v-else-if="current">
        <p class="font-semibold break-all">当前核对：{{ current.order_id }}</p>
        <p>{{ channelLabel(current.payment_channel, current.device_platform) }} · 实收 {{ yuan(current.amount_fen) }}</p>
        <div v-if="currentBill" class="rounded bg-elevated p-3 space-y-2 text-sm"><p v-if="currentBill.wechat_reconciliation">微信日账单：{{ currentBill.wechat_reconciliation.differences.length ? currentBill.wechat_reconciliation.differences.join('；') : '收退款字段一致，手续费仍需核对' }}</p><p v-if="currentBill.bill_row_id">导入账单手续费：{{ yuan(currentBill.channel_fee_fen ?? 0) }} · {{ currentBill.differences.length ? currentBill.differences.join('；') : '关键字段一致' }}</p><UCheckbox v-if="currentBill.can_adopt" v-model="useBill" label="采用这笔账单的实际手续费金额" :disabled="busy" @update:model-value="confirmed = false" /></div>
        <UFormField v-if="!useBill" label="实际支付渠道手续费率（%）" required><UInput v-model="channelRate" inputmode="decimal" required :disabled="busy" @update:model-value="confirmed = false" /></UFormField>
        <SettlementFees v-model="fees" label="共同费用" references allow-percent :disabled="busy" />
        <RewardCalculation :amount="current.amount_fen" :channel="input?.channel ?? null" :channel-rate="input?.channelRate" :fees="input?.fees ?? null" :rate="current.policy.rate_bps" :cap="current.policy.max_reward_fen" />
        <p v-if="input" class="font-semibold">税前奖励：{{ yuan(calculateReward(current.amount_fen, input.channel, input.fees, current.policy.rate_bps, current.policy.max_reward_fen).commission) }}</p>
      </template>
      <UFormField label="核对依据 / 凭据编号" required><UTextarea v-model="evidence" minlength="2" maxlength="1000" required :disabled="busy" class="w-full" /></UFormField>
      <UCheckbox :key="batch ? 'batch' : 'single'" v-model="confirmed" :label="batch ? '已逐单核实本批费用规则与实际账单一致，无重复扣费' : '已据实核对全部费用及凭据，无重复扣费'" :disabled="busy" />
      <UButton :label="batch ? '确认批量核对 ' + remaining.length + ' 笔' : '保存并核对下一笔'" type="submit" :loading="busy" :disabled="busy || !confirmed || evidence.trim().length < 2 || (batch ? !!batchUnknown || !!batchConflicts || !remaining.length : !input)" class="self-start" />
    </form>
  </section>
</template>
