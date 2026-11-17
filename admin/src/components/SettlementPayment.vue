<script setup lang="ts">
import { computed, ref } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { yuan } from '../growth'
import { financeGrant } from '../promotion-finance'
import { statementDetail } from '../settlement-operations'
import { moneyFen, recordSettlementPayment, type Statement } from '../settlements'
import SettlementCalculation from './SettlementCalculation.vue'
import SettlementEvidence from './SettlementEvidence.vue'

const props = defineProps<{ user: UserInfo; id: string }>()
const emit = defineEmits<{ close: []; updated: []; batch: [id: string] }>()
const item = ref<Statement | null>(null), batchId = ref(''), blocked = ref(true), evidenceBusy = ref(false)
const amount = ref(''), receipt = ref(''), transferredAt = ref('')
const canPay = computed(() => financeGrant(props.user, 'Payout'))
const page = useAdminPage(async valid => {
  const value = await statementDetail(props.id)
  if (valid()) { item.value = value.statement; batchId.value = value.payout_batch_id || '' }
})
function save() {
  void page.act(async valid => {
    if (!item.value || blocked.value || batchId.value || item.value.status !== 'approved') throw new Error('请先核对收款资料、账单及付款批次')
    const actual = moneyFen(amount.value), expected = Math.max(0, item.value.net_fen ?? 0)
    if (actual !== expected) throw new Error('实际付款金额必须与本次应付一致')
    if (expected > 0 && !transferredAt.value) throw new Error('请填写实际付款时间')
    const at = transferredAt.value ? Math.floor(new Date(transferredAt.value).getTime() / 1000) : undefined
    if (at !== undefined && !Number.isFinite(at)) throw new Error('实际付款时间无效')
    const value = await recordSettlementPayment(props.user.id, item.value, actual, receipt.value, at)
    if (valid()) { item.value = value; emit('updated'); emit('close') }
  })
}
</script>
<template>
  <UModal :open="true" title="登记已完成的付款" :dismissible="!page.busy.value && !evidenceBusy" :close="!page.busy.value && !evidenceBusy" @update:open="value => { if (!value && !page.busy.value && !evidenceBusy) emit('close') }">
    <template #body><div class="field-stack">
      <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
      <UButton label="刷新本单付款检查" variant="outline" :disabled="page.busy.value || evidenceBusy" :loading="page.loading.value" @click="page.load" />
      <p v-if="!item">{{ page.loading.value ? '正在读取结算单…' : '结算单暂不可用，请刷新重试' }}</p>
      <template v-if="item">
        <p class="promotion-wrap">{{ item.beneficiary_name }} · {{ item.id }}</p>
        <SettlementCalculation :gross="item.gross_fen" :adjustment="item.adjustment_fen" :fees="item.review?.personal_fees ?? null" :tax="item.tax_fen" :net="item.net_fen" />
        <SettlementEvidence :actor="user.id" :item="item" :finance="true" :payee-access="canPay" :file-access="canPay" purpose="payment" @updated="item = $event" @busy="evidenceBusy = $event" @blocked="blocked = $event" />
        <UButton v-if="batchId" label="前往原付款批次" icon="i-lucide-list" :disabled="page.busy.value || evidenceBusy" @click="emit('batch', batchId)" />
        <form v-if="canPay && item.status === 'approved' && !batchId" class="field-stack" @submit.prevent="save">
          <p class="font-semibold">本次应付 {{ yuan(Math.max(0, item.net_fen ?? 0)) }}</p>
          <p class="text-xs text-muted">登记已完成的转账；请核对本单留存的收款账号与银行回单。零元结算填写核销凭据。</p>
          <UFormField label="实际付款时间（本机时区）" :required="(item.net_fen ?? 0) > 0"><UInput v-model="transferredAt" type="datetime-local" :required="(item.net_fen ?? 0) > 0" :disabled="page.busy.value || evidenceBusy" /></UFormField>
          <UFormField label="实际付款金额（元）" required><UInput v-model="amount" inputmode="decimal" required :disabled="page.busy.value || evidenceBusy" /></UFormField>
          <UFormField label="转账流水号 / 核销凭据" required><UInput v-model="receipt" required minlength="2" maxlength="500" :disabled="page.busy.value || evidenceBusy" /></UFormField>
          <UButton label="确认登记付款" type="submit" :loading="page.busy.value" :disabled="page.busy.value || page.loading.value || evidenceBusy || blocked" />
        </form>
        <p v-else-if="item.status === 'paid'" class="text-success">此结算单已付款，无需再次登记。</p>
        <p v-else-if="item.status !== 'approved'" class="text-warning">此结算单尚未审核或已作废，请返回结算管理处理。</p>
      </template>
    </div></template>
  </UModal>
</template>
