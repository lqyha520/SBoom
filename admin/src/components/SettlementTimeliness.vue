<script setup lang="ts">
import type { SettlementSummary, SettlementTiming } from '../settlement-operations'
defineProps<{ summary: SettlementSummary; disabled?: boolean }>()
defineEmits<{ select: [timing: SettlementTiming] }>()
</script>
<template>
  <div class="actions-row" aria-label="结算处理时效">
    <UButton v-if="summary.stalled ?? summary.overdue" :label="(summary.stalled ?? summary.overdue) + ' 份申请超过三天未更新'" color="warning" variant="link" :disabled="disabled" @click="$emit('select', 'stalled')" />
    <UButton v-if="summary.review_overdue" :label="summary.review_overdue + ' 份申请超过审核目标'" color="warning" variant="link" :disabled="disabled" @click="$emit('select', 'review_overdue')" />
    <UButton v-if="summary.payout_overdue" :label="summary.payout_overdue + ' 份申请超过付款目标'" color="warning" variant="link" :disabled="disabled" @click="$emit('select', 'payout_overdue')" />
  </div>
</template>
