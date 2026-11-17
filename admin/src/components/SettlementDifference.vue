<script setup lang="ts">
import { yuan } from '../growth'
import type { Difference } from '../settlement-operations'
defineProps<{ value: Difference }>()
const amount = (value: number | null) => value === null ? '待核对' : yuan(value)
const delta = (before: number | null, after: number | null) => before === null || after === null ? '待核对' : yuan(after - before)
</script>
<template>
  <details class="rounded border border-default p-3" open><summary class="cursor-pointer font-medium">申请参考与核定金额对比</summary>
    <p class="text-sm mt-3">税前奖励：{{ amount(value.reference_gross_fen) }} → {{ amount(value.actual_gross_fen) }}；历史调整：{{ yuan(value.adjustment_before_fen) }} → {{ amount(value.adjustment_after_fen) }}</p>
    <p v-if="value.reason" class="text-sm whitespace-pre-wrap">差异说明：{{ value.reason }}</p>
    <details class="mt-3"><summary class="cursor-pointer text-sm">查看逐笔变化</summary><div class="data-scroll"><table class="data-table"><thead><tr><th>订单 / 项目</th><th>申请参考</th><th>当前核定</th><th>增减</th></tr></thead><tbody><template v-for="row in value.items" :key="row.order_id"><tr><td class="break-all">{{ row.order_id }} · 税前奖励</td><td>{{ amount(row.before_fen) }}</td><td>{{ amount(row.after_fen) }}</td><td>{{ delta(row.before_fen, row.after_fen) }}</td></tr><tr><td>渠道手续费</td><td>{{ amount(row.channel_before_fen) }}</td><td>{{ amount(row.channel_after_fen) }}</td><td>{{ delta(row.channel_before_fen, row.channel_after_fen) }}</td></tr><tr v-for="fee in row.fees" :key="fee.name"><td>{{ fee.name }}</td><td>{{ amount(fee.before_fen) }}</td><td>{{ amount(fee.after_fen) }}</td><td>{{ delta(fee.before_fen, fee.after_fen) }}</td></tr></template></tbody></table></div></details>
    <p class="text-xs text-muted mt-2">个人费用与实际代扣个税在审核时核定，完整扣费和最终到手见下方计算过程。</p>
  </details>
</template>
