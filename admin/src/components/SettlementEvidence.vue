<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useAdminRefresh } from '../admin-page'
import { attachPayee, revealPayee, payeeMethods, uploadEvidence, downloadEvidence, statementDetail, type Payee, type Attachment, type BillDifference } from '../settlement-operations'
import { dateTime } from '../growth'
import type { Statement } from '../settlements'
const props = defineProps<{ actor: number; item: Statement; finance: boolean; purpose?: 'review' | 'payment'; payeeAccess?: boolean; fileAccess?: boolean }>()
const emit = defineEmits<{ updated: [item: Statement]; busy: [value: boolean]; blocked: [value: boolean] }>()
const files = ref<Attachment[]>([]), fullPayee = ref<Payee | null>(null), busy = ref(false), error = ref('')
const differences = ref<BillDifference[]>([])
let sequence = 0
onBeforeUnmount(() => { sequence++ })
async function load() {
  const ticket = ++sequence, id = props.item.id
  emit('blocked', true); error.value = ''
  try {
    const value = await statementDetail(id)
    if (ticket !== sequence) return
    files.value = value.attachments; differences.value = [...(value.bill_differences ?? [])]
    const purpose = props.purpose === 'review' ? 'review' : 'payment'
    differences.value.push(...(value.operation_issues ?? []).filter(item => !item.purpose || item.purpose === purpose))
    if (value.statement.revision !== props.item.revision) emit('updated', value.statement)
    emit('blocked', differences.value.length > 0 || (props.purpose === 'review' ? value.statement.status !== 'draft' : (value.statement.net_fen ?? 0) > 0 && !value.statement.snapshot.payee))
  } catch (e) { if (ticket === sequence) error.value = e instanceof Error ? e.message : '读取凭证失败' }
}
async function run(operation: () => Promise<unknown>) { busy.value = true; emit('busy', true); error.value = ''; try { await operation() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败' } finally { busy.value = false; emit('busy', false) } }
function attach() { void run(async () => { emit('updated', await attachPayee(props.actor, props.item)) }) }
function reveal() { void run(async () => { fullPayee.value = await revealPayee(props.actor, props.item.id) }) }
function upload(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (file) void run(async () => { await uploadEvidence(props.actor, props.item.id, file); input.value = ''; await load() }) }
watch(() => [props.item.id, props.item.revision], () => { fullPayee.value = null; void load() })
useAdminRefresh(load, () => { sequence++; fullPayee.value = null })
</script>
<template>
  <section class="rounded border border-default p-3 space-y-3" :aria-label="purpose === 'review' ? '审核前账单检查' : '收款与付款凭证'">
    <p class="font-medium">{{ purpose === 'review' ? '审核前账单检查' : '本次收款资料与凭证' }}</p><UAlert v-if="error" :title="error" color="error" />
    <UButton :label="purpose === 'review' ? '刷新审核账单检查' : '刷新付款资料与账单检查'" variant="ghost" :disabled="busy" @click="load" />
    <UAlert v-if="purpose === 'review' && item.status !== 'draft'" title="此结算单已不处于待审核状态，请关闭窗口并刷新列表。" color="warning" />
    <div v-if="finance && differences.length" role="alert" class="text-warning space-y-1"><p>账单、异议或复核规则尚有阻塞，请按下方原因处理后刷新。</p><p v-for="(item, index) in differences" :key="index" class="break-all">{{ item.order_id }}：{{ item.reasons.join('；') }}</p></div>
    <template v-if="item.snapshot.payee"><p>{{ item.snapshot.payee.name }} · {{ payeeMethods[item.snapshot.payee.method] }} · {{ fullPayee?.account || item.snapshot.payee.account }}</p><p v-if="item.snapshot.payee.bank">{{ item.snapshot.payee.bank }}</p><div class="actions-row"><UButton v-if="finance && payeeAccess !== false && !fullPayee" label="查看完整收款账号" variant="outline" :disabled="busy" @click="reveal" /><UButton v-if="fullPayee" label="隐藏完整账号" variant="outline" @click="fullPayee = null" /></div></template>
    <template v-else><p>本结算单未留存收款资料。非零付款须先在“收款资料”保存，再留存到此单；零元核销无需收款账号。</p><UButton v-if="finance && payeeAccess !== false && ['draft','approved'].includes(item.status)" label="留存当前收款资料" variant="outline" :disabled="busy" @click="attach" /></template>
    <p v-if="item.payout?.transferred_at">实际付款时间：{{ dateTime(item.payout.transferred_at) }}</p><p v-else-if="item.status === 'paid'">{{ (item.net_fen ?? 0) <= 0 ? '零元核销无需实际转账时间' : '历史记录未填写实际付款时间' }}；登记时间：{{ dateTime(item.paid_at ?? 0) }}</p>
    <p v-if="item.receipt" class="break-all">转账流水号：{{ item.receipt }}</p>
    <ul v-if="files.length" class="space-y-2"><li v-for="file in files" :key="file.id"><UButton :label="file.name" variant="link" :disabled="busy" @click="run(() => downloadEvidence(file))" /> · {{ dateTime(file.created_at) }}</li></ul><p v-else class="text-xs text-muted">暂无凭证附件</p>
    <UFormField v-if="finance && fileAccess !== false && item.status !== 'void'" label="添加付款凭证（PNG / JPEG / PDF，单份不超过 2MB，最多 5 份）"><input type="file" accept="image/png,image/jpeg,application/pdf" :disabled="busy || files.length >= 5" @change="upload"></UFormField>
  </section>
</template>
