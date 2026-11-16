<script setup lang="ts">
import { computed } from 'vue'
import { yuan } from '../growth'
import { personalBasisNames, resolvePersonalFees, type PersonalFee } from '../settlements'
const props = defineProps<{ gross: number; adjustment: number; fees: PersonalFee[] | null; tax: number | null; net?: number | null }>()
const resolved = computed(() => props.fees === null ? null : resolvePersonalFees(props.fees, props.gross, props.adjustment))
const personal = computed(() => resolved.value === null ? null : resolved.value.reduce((sum, fee) => sum + fee.amount_fen, 0))
const netAmount = computed(() => props.net ?? (personal.value === null || props.tax === null ? null : props.gross + props.adjustment - personal.value - props.tax))
</script>

<template>
  <div class="rounded border border-default p-3 text-sm space-y-2" aria-label="管理员到手金额计算过程">
    <p class="font-semibold">税前奖励到最终到手金额</p>
    <p>结算余额 = 税前奖励合计 + 历史调整 − 个人费用合计 − 实际代扣个税</p>
    <p>税前奖励合计：{{ yuan(gross) }}</p>
    <p>历史调整：{{ adjustment >= 0 ? '+' : '−' }}{{ yuan(Math.abs(adjustment)) }}（正数补付，负数扣回）</p>
    <p v-for="(fee, index) in resolved" :key="index">个人费用 · {{ fee.name }}：<template v-if="fee.mode === 'percent'">{{ personalBasisNames[fee.basis ?? 'reward_gross'] }} {{ yuan(fee.base_fen) }} × {{ (fee.rate_bps ?? 0) / 100 }}% = </template><template v-else>固定金额 </template>{{ yuan(fee.amount_fen) }}<span v-if="fee.source_ref" class="text-xs text-muted promotion-wrap"> · 凭据关联 {{ fee.source_ref }}</span>（扣除）</p>
    <p>个人费用合计：{{ personal === null ? '待核对' : yuan(personal) }}</p>
    <p>实际代扣个税：{{ tax === null ? '待核定' : yuan(tax) }}</p>
    <template v-if="netAmount !== null && personal !== null && tax !== null">
      <p>结算余额：{{ yuan(gross) }} {{ adjustment >= 0 ? '+' : '−' }} {{ yuan(Math.abs(adjustment)) }} − {{ yuan(personal) }} − {{ yuan(tax) }} = {{ yuan(netAmount) }}</p>
      <p class="font-semibold">最终到手：max(0，{{ yuan(netAmount) }}) = {{ yuan(Math.max(0, netAmount)) }}</p>
      <p v-if="netAmount < 0">剩余扣回 {{ yuan(-netAmount) }}，零元核销后结转下期。</p>
    </template>
    <p v-else>最终到手：待核对个人费用和个税，未填写不按零计算。</p>
  </div>
</template>
