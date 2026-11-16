<script setup lang="ts">
import { computed } from 'vue'
import { channelLabel, type ApplicationSnapshot, type SharedFee } from '../settlements'
import RewardRates from './RewardRates.vue'

const props = defineProps<{ items: ApplicationSnapshot['items'] }>()
const groups = computed(() => {
  const result = new Map<string, { label: string; count: number; channelRate: number | null; rate: number; fees: SharedFee[]; confirmed: boolean }>()
  for (const item of props.items) {
    const group = { label: channelLabel(item.payment_channel, item.device_platform), channelRate: item.reference_channel_rate_bps ?? null,
      rate: item.policy.rate_bps, confirmed: !!item.costs, fees: item.reference_fees.map(fee => fee.mode === 'percent'
        ? { name: fee.name, mode: fee.mode, rate_bps: fee.rate_bps, basis: fee.basis ?? 'after_channel' }
        : { name: fee.name, amount_fen: fee.amount_fen }) }
    const key = JSON.stringify(group)
    const existing = result.get(key)
    if (existing) existing.count++
    else result.set(key, { ...group, count: 1 })
  }
  return [...result.entries()]
})
</script>

<template>
  <section v-if="groups.length" class="space-y-3" aria-label="本次申请扣费比例">
    <p class="font-semibold">本次申请的扣费与奖励比例</p>
    <p class="text-xs text-muted">按各笔订单的规则分别展示；同渠道规则不同时分组列出。已核对订单使用核定费用，其余使用下单时的参考规则。</p>
    <div v-for="[key, group] in groups" :key="key" class="rounded border border-default p-3 space-y-2">
      <p class="font-medium">{{ group.label }} · {{ group.count }} 笔 · {{ group.confirmed ? '费用已核对' : '参考费率，待对账' }}</p>
      <RewardRates :channel-rate="group.channelRate" :fees="group.fees" :rate="group.rate" :confirmed="group.confirmed" />
    </div>
  </section>
</template>
