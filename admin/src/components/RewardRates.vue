<script setup lang="ts">
import { yuan } from '../growth'
import { feeBasisNames, type SharedFee } from '../settlements'

defineProps<{ channelRate?: number | null; fees: SharedFee[] | null; rate: number; confirmed?: boolean }>()
</script>

<template>
  <dl class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs whitespace-normal break-words" aria-label="本单扣费与奖励比例">
    <div class="min-w-0 rounded bg-elevated p-2">
      <dt class="text-muted">渠道手续费</dt>
      <dd class="mt-1 font-semibold text-lg tabular-nums">{{ channelRate == null ? (confirmed ? '按账单' : '待核对') : channelRate / 100 + '%' }}</dd>
      <dd class="text-muted">{{ channelRate == null ? (confirmed ? '历史未记录费率' : '未记录费率') : '按订单实收' }}</dd>
    </div>
    <div v-for="(fee, index) in fees" :key="index" class="min-w-0 rounded bg-elevated p-2">
      <dt class="text-muted break-words">{{ fee.name }}</dt>
      <dd class="mt-1 font-semibold text-lg tabular-nums">{{ fee.mode === 'percent' ? (fee.rate_bps ?? 0) / 100 + '%' : yuan(fee.amount_fen ?? 0) }}</dd>
      <dd class="text-muted">{{ fee.mode === 'percent' ? '按' + feeBasisNames[fee.basis ?? 'after_channel'] : '固定金额 / 单' }}</dd>
    </div>
    <div v-if="!fees?.length" class="min-w-0 rounded bg-elevated p-2">
      <dt class="text-muted">共同费用</dt>
      <dd class="mt-1 font-semibold text-lg">{{ fees === null ? '待核对' : '无' }}</dd>
    </div>
    <div class="min-w-0 rounded bg-primary/10 p-2">
      <dt class="text-muted">奖励比例</dt>
      <dd class="mt-1 font-semibold text-lg text-primary tabular-nums">{{ rate / 100 }}%</dd>
      <dd class="text-muted">按扣除共同费用后的金额</dd>
    </div>
  </dl>
</template>
