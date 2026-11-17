<script setup lang="ts">
import { yuan } from '../growth'
import type { ChannelTotal } from '../settlements'
defineProps<{ channels: ChannelTotal[]; reference?: boolean }>()
const amount = (value: number | null) => value === null ? '待核对' : yuan(value)
</script>

<template>
  <div aria-label="分渠道结算汇总" class="space-y-3 text-sm">
    <p class="font-semibold">分渠道{{ reference ? '参考' : '' }}汇总（逐单计算后相加）</p>
    <div v-for="group in channels" :key="group.key" class="rounded border border-default p-3 space-y-1">
      <p class="font-semibold">{{ group.label }} · {{ group.orders }} 笔</p>
      <p>实收 {{ yuan(group.amount_fen) }} · 渠道费 {{ amount(group.unknown_rates ? null : group.channel_fen) }}</p>
      <p>共同费用 {{ amount(group.unknown_rates ? null : group.shared_fen) }} · 税前奖励 {{ amount(group.unknown_rates ? null : group.commission_fen) }}</p>
      <p v-if="group.unknown_rates" class="text-muted">其中 {{ group.unknown_rates }} 笔渠道费率未知，本组费用和奖励合计待核对。</p>
    </div>
  </div>
</template>
