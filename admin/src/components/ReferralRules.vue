<script setup lang="ts">
import { ref } from 'vue'
import { request } from '../api'
import { useAdminPage } from '../admin-page'
import { yuan } from '../growth'
import { type RewardPolicy } from '../settlements'
import RewardRates from './RewardRates.vue'
const props = withDefaults(defineProps<{ area?: 'referrals' | 'settlements'; expanded?: boolean }>(), { area: 'referrals' })
const rules = ref<RewardPolicy | null>(null)
const page = useAdminPage(async valid => { const value = await request<RewardPolicy>(`/api/v1/admin/${props.area}/rules`); if (valid()) rules.value = value })
</script>
<template>
  <details :open="expanded || area === 'referrals'" class="rounded border border-default p-4 mb-4 space-y-3" aria-label="邀请与奖励规则">
    <summary class="cursor-pointer font-medium">推广规则与结算时效</summary>
    <div class="actions-row justify-between"><h3 class="font-semibold">推广前先看奖励规则</h3><UButton label="刷新奖励规则" variant="ghost" size="xs" :loading="page.loading.value" @click="page.load" /></div>
    <p class="text-sm">新用户首次注册绑定推广来源，后续扫码不会改绑。普通用户转发会延续已有管理员归属；现金奖励归属推广管理员，邀请用户本人不因此获得现金或试用权益。</p>
    <UAlert v-if="page.error.value" :title="'奖励规则读取失败：' + page.error.value" color="error" />
    <p v-else-if="page.loading.value" role="status">正在读取奖励规则…</p>
    <template v-else-if="rules">
      <UAlert v-if="!rules.enabled" title="当前未启用新订单推广奖励，注册归属仍正常记录" color="warning" />
      <p class="text-sm font-medium">首付奖励 {{ rules.rate_bps / 100 }}% · 支付后等待 {{ rules.hold_days }} 天 · 单笔{{ rules.max_reward_fen == null ? '未设置奖励上限' : '奖励上限 ' + yuan(rules.max_reward_fen) }}</p>
      <p class="text-sm">每位客户仅首次成功付费产生奖励，续费不奖励；首次付款退款后不恢复资格。下单时保存奖励规则，之后改规则不回算旧订单。</p>
      <details><summary class="cursor-pointer text-sm">渠道费、共同费用和到手金额怎么算</summary><div class="space-y-3 mt-3 text-sm">
        <p>税前奖励 = max(0，订单实收 − 渠道手续费 − 约定共同费用) × 奖励比例，并按单笔上限封顶。</p>
        <p>最终应付 = max(0，核定税前奖励 + 历史调整 − 个人费用 − 实际代扣税款)。申请中的参考奖励不等于到手金额。</p>
        <template v-if="rules.channel_rates"><p>当前参考渠道费率：普通微信 {{ rules.channel_rates.wechat / 100 }}%；安卓等虚拟支付 {{ rules.channel_rates.virtual_android / 100 }}%；iOS 虚拟支付 {{ rules.channel_rates.virtual_ios / 100 }}%。</p></template>
        <p v-if="rules.channel_rates">以下以普通微信渠道展示费用定义：</p>
        <RewardRates :channel-rate="rules.channel_rates?.wechat ?? rules.channel_rate_bps" :fees="rules.shared_fees" :rate="rules.rate_bps" :confirmed="false" />
        <p>渠道费以实际账单核对；共同费用列明名称与基数，个人费用和个税另行核定，未知金额显示待核对。已发奖励遇退款会进入后续结算扣回。</p>
      </div></details>
      <div class="rounded bg-elevated p-3 space-y-1 text-sm">
        <p>审核处理目标：{{ rules.review_days == null ? '尚未设置，提交前请与财务明确' : '提交申请后 ' + rules.review_days + ' 个自然日内完成对账审核' }}。</p>
        <p>付款处理目标：{{ rules.payout_days == null ? '尚未设置，审核后请关注付款进度' : '审核通过后 ' + rules.payout_days + ' 个自然日内安排付款' }}。</p>
        <p class="text-xs text-muted">处理目标用于新申请，按提交时规则留档；实际到账时间以转账结果为准。等待期未满、退款或订单异常需先处理。</p>
      </div>
    </template>
  </details>
</template>
