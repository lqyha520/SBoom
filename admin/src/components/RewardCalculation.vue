<script setup lang="ts">
import { computed } from 'vue'
import { yuan } from '../growth'
import { calculateReward, feeBasisNames, type SharedFee } from '../settlements'
import RewardRates from './RewardRates.vue'
const props = defineProps<{ amount: number; channel: number | null; channelRate?: number | null; fees: SharedFee[] | null; rate: number; commission?: number | null; estimated?: boolean; cap?: number | null }>()
const unknown = computed(() => props.channel === null || (props.estimated && props.channelRate == null))
const result = computed(() => unknown.value || props.fees === null ? null : calculateReward(props.amount, props.channel!, props.fees, props.rate, props.cap))
</script>

<template>
  <div class="rounded border border-default p-3 text-sm space-y-2" aria-label="订单奖励计算过程">
    <p class="font-semibold">{{ estimated ? '参考奖励计算（费用尚未核对）' : '订单实收到税前奖励' }}</p>
    <RewardRates :channel-rate="channelRate" :fees="fees" :rate="rate" :confirmed="!estimated && channel !== null" />
    <p v-if="estimated" class="text-sm">{{ unknown ? '本单未记录渠道费率，参考奖励待核对' : '渠道费按下单时费率试算' }}，共同费用使用下单时的规则，实际扣费待对账。以下参考奖励不是承诺到手金额。</p>
    <p>税前奖励 = max(0，实收 − 支付渠道费 − 共同费用合计) × 奖励比例</p>
    <p>订单实收：{{ yuan(amount) }}</p>
    <p v-if="channelRate != null && channel !== null">{{ estimated ? '参考支付渠道费' : '支付渠道费' }}：订单实收 {{ yuan(amount) }} × {{ channelRate / 100 }}% = {{ yuan(channel) }}{{ estimated ? '（待对账）' : '' }}</p>
    <p v-else>支付渠道费：{{ unknown ? '待核对' : yuan(channel!) + '（历史按账单金额核对）' }}</p>
    <template v-if="result">
      <p>扣支付手续费后金额：max(0，{{ yuan(amount) }} − {{ yuan(channel!) }}) = {{ yuan(result.afterChannel) }}</p>
      <p v-for="(fee, index) in result.fees" :key="index">
        {{ fee.name }}：<template v-if="fee.mode === 'percent'">{{ feeBasisNames[fee.basis || 'after_channel'] }} {{ yuan(fee.base_fen) }} × {{ (fee.rate_bps || 0) / 100 }}% = </template><template v-else>固定金额 </template>{{ yuan(fee.amount_fen) }}<span v-if="fee.source_ref" class="text-xs text-muted promotion-wrap"> · 凭据关联 {{ fee.source_ref }}</span>
      </p>
      <p v-if="!result.fees.length">其他共同费用：无</p>
      <p>共同费用合计：{{ result.fees.map(fee => yuan(fee.amount_fen)).join(' + ') || yuan(0) }} = {{ yuan(result.shared) }}</p>
      <p>分成基数：max(0，{{ yuan(amount) }} − {{ yuan(channel!) }} − {{ yuan(result.shared) }}) = {{ yuan(result.distributable) }}</p>
      <p v-if="cap != null">本单奖励上限：{{ yuan(cap) }}，按计算奖励与上限中的较小值发放。</p>
      <p class="font-semibold">{{ estimated ? '参考税前奖励' : '税前奖励' }}：{{ cap != null ? 'min（' : '' }}{{ yuan(result.distributable) }} × {{ rate / 100 }}%{{ cap != null ? '，' + yuan(cap) + '）' : '' }} = {{ yuan(commission ?? result.commission) }}</p>
    </template>
    <p v-else>费用填写并核对后显示具体结果；奖励比例 {{ rate / 100 }}%。</p>
    <p class="text-xs text-muted">渠道费按费率计算后四舍五入到分；其他比例费用及单笔奖励不足一分舍去。个人费用、个税和历史调整在结算单汇总。</p>
  </div>
</template>
