<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { applySettlement, previewApplication, type ApplicationQuote } from '../settlements'
import SettlementApplicationSummary from './SettlementApplicationSummary.vue'
const props = defineProps<{ actor: number; orderIds: string[]; allEligible?: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const open = ref(true), loading = ref(true), busy = ref(false), confirmed = ref(false), error = ref(''), note = ref('')
const quote = ref<ApplicationQuote | null>(null), key = crypto.randomUUID()
let alive = true
onUnmounted(() => { alive = false })
async function load() {
  loading.value = true; error.value = ''; confirmed.value = false; quote.value = null
  try { const value = await previewApplication(props.orderIds, props.allEligible); if (alive) quote.value = value }
  catch (e) { if (alive) error.value = e instanceof Error ? e.message : '读取申请明细失败' }
  finally { if (alive) loading.value = false }
}
async function submit() {
  if (busy.value || !confirmed.value || !quote.value?.snapshot.items.length) return
  busy.value = true; error.value = ''
  try {
    await applySettlement(props.actor, { ...(props.allEligible ? { all_eligible: true } : { order_ids: props.orderIds }), request_key: key, quote_digest: quote.value.quote_digest, note: note.value, confirmed: true })
    if (alive) { emit('saved'); emit('close') }
  } catch (e) { if (alive) { error.value = e instanceof Error ? e.message : '提交申请失败'; confirmed.value = false } }
  finally { if (alive) busy.value = false }
}
onMounted(load)
</script>

<template>
  <UModal v-model:open="open" title="申请推广结算" :dismissible="!busy" :close="!busy" @after:leave="emit('close')">
    <template #body>
      <UAlert v-if="error" :title="error" color="error" class="mb-3" />
      <UButton v-if="error" label="重新核对申请明细" variant="outline" :disabled="busy || loading" @click="load" />
      <p v-if="loading" role="status">正在计算奖励与扣费明细…</p>
      <form v-else-if="quote" class="field-stack" @submit.prevent="submit">
        <SettlementApplicationSummary :snapshot="quote.snapshot" />
        <p v-if="!quote.snapshot.items.length">暂无可申请订单，未满等待期或退款处理中订单可在条件满足后再次申请。</p>
        <UFormField label="申请备注"><UTextarea v-model="note" maxlength="500" :disabled="busy" class="w-full" /></UFormField>
        <UCheckbox v-model="confirmed" label="已了解奖励和扣费明细，待核费用及最终应付以对账审核为准" :disabled="busy" />
        <UButton label="确认提交申请" type="submit" :loading="busy" :disabled="busy || !confirmed || !quote.snapshot.items.length" />
      </form>
    </template>
  </UModal>
</template>
