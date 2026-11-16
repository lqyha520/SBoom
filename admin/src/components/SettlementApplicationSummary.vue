<script setup lang="ts">
import { computed } from 'vue'
import { dateTime, yuan } from '../growth'
import { channelLabel } from '../settlements'
import type { ApplicationSnapshot } from '../settlements'
import RewardCalculation from './RewardCalculation.vue'
import SettlementChannels from './SettlementChannels.vue'
import SettlementRateSummary from './SettlementRateSummary.vue'
const props = defineProps<{ snapshot: ApplicationSnapshot }>()
const unknownOrders = computed(() => props.snapshot.items.filter(item => !item.costs && item.reference_channel_rate_bps == null).length)
const knownGross = computed(() => props.snapshot.items.reduce((total, item) => total + (!item.costs && item.reference_channel_rate_bps == null ? 0 : item.reference_commission_fen ?? 0), 0))
</script>

<template>
  <div class="field-stack text-sm" aria-label="申请时奖励与扣费明细">
    <p>订单 {{ snapshot.items.length }} 笔，费用尚未核对 {{ snapshot.unconfirmed_orders }} 笔。申请后由超级管理员核对实际扣费并确定最终应付。</p>
    <SettlementRateSummary :items="snapshot.items" />
    <SettlementChannels v-if="snapshot.channels?.length" :channels="snapshot.channels" reference />
    <details :open="snapshot.items.length <= 5" class="space-y-3">
      <summary class="cursor-pointer font-medium">逐单扣费与奖励（{{ snapshot.items.length }} 笔）</summary>
      <div v-for="item in snapshot.items" :key="item.order_id" class="mt-3">
        <p class="break-all mb-2">订单 {{ item.order_id }} · {{ item.costs ? '订单费用已核对' : '费用待对账，以下为参考' }}</p>
        <p v-if="item.payment_channel">{{ channelLabel(item.payment_channel, item.device_platform) }}</p>
        <RewardCalculation :amount="item.amount_fen" :channel="item.reference_channel_fen" :channel-rate="item.reference_channel_rate_bps" :fees="item.reference_fees" :rate="item.policy.rate_bps" :cap="item.policy.max_reward_fen" :commission="item.reference_commission_fen" :estimated="!item.costs" />
      </div>
    </details>
    <details v-if="snapshot.excluded?.length" class="rounded border border-default p-3">
      <summary class="cursor-pointer font-medium">本次未纳入 {{ snapshot.excluded.length }} 笔，查看原因</summary>
      <p v-for="item in snapshot.excluded" :key="item.order_id" class="break-all mt-2">{{ item.order_id }}：{{ item.reason }}。等待期结束：{{ dateTime(item.available_at) }}</p>
      <p class="mt-2">未满等待期或退款待处理的订单，条件满足后可再次合并申请；已结算订单不会重复奖励。</p>
    </details>
    <div class="rounded border border-default p-3 space-y-2">
      <template v-if="unknownOrders || snapshot.reference_gross_fen === null">
        <p class="font-semibold">申请时参考税前奖励合计：待核对</p>
        <p>{{ unknownOrders }} 笔订单渠道费率未知，暂不计算完整奖励。其余订单参考税前奖励小计：{{ yuan(knownGross) }}。</p>
      </template>
      <p v-else>申请时{{ snapshot.unconfirmed_orders ? '参考' : '' }}税前奖励合计：{{ snapshot.items.length <= 5 ? snapshot.items.map(item => yuan(item.reference_commission_fen!)).join(' + ') : snapshot.items.length + ' 笔逐单奖励相加' }} = {{ yuan(snapshot.reference_gross_fen) }}</p>
      <p v-for="item in snapshot.adjustments" :key="item.id">历史调整：{{ yuan(item.amount_fen) }} · {{ item.reason }}</p>
      <p>历史调整合计：{{ yuan(snapshot.adjustment_fen) }}（正数补付，负数扣回）</p>
      <p v-if="unknownOrders || snapshot.reference_gross_fen === null || snapshot.reference_after_adjustment_fen === null">扣个人费用、个税前参考余额：待核对。可先提交申请，由财务补齐费用后核定。</p>
      <p v-else>扣个人费用、个税前参考余额：max(0，{{ yuan(snapshot.reference_gross_fen) }} + {{ yuan(snapshot.adjustment_fen) }}) = {{ yuan(snapshot.reference_after_adjustment_fen) }}</p>
      <p>审核处理目标：{{ snapshot.service_terms?.review_days == null ? '尚未设置，请与财务明确' : '提交后 ' + snapshot.service_terms.review_days + ' 个自然日' }}；付款处理目标：{{ snapshot.service_terms?.payout_days == null ? '尚未设置' : '审核通过后 ' + snapshot.service_terms.payout_days + ' 个自然日' }}。</p>
      <p>个人承担费用：待对账确认。</p>
      <p>实际代扣个人所得税：待核定。</p>
      <p class="font-semibold">最终到手 = max(0，核定税前奖励 + 历史调整 − 个人费用 − 实际个税)。申请时最终应付待审核。</p>
      <p class="text-xs text-muted">提交时明细会保留；对账期间的费用核定、退款和新增扣回可能改变结果。审核后可在同一申请查看最终结算明细。</p>
    </div>
  </div>
</template>
