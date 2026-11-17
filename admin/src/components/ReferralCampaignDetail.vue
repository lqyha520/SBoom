<script setup lang="ts">
import { onActivated, onDeactivated, ref, watch } from 'vue'
import { useAdminPage } from '../admin-page'
import { campaignPerformance, type CampaignPerformance } from '../referral-operations'
import { yuan } from '../growth'
import { referenceRewardLabel } from '../referrals'
import ReferralExpenseLedger from './ReferralExpenseLedger.vue'
const props = defineProps<{ id: string; initialExpenses?: boolean }>()
const emit = defineEmits<{ close: []; select: [id: string, admin: string] }>()
const value = ref<CampaignPerformance | null>(null)
const active = ref(true)
onActivated(() => { active.value = true })
onDeactivated(() => { active.value = false })
const expensesOpen = ref(!!props.initialExpenses)
const page = useAdminPage(async valid => { if (!props.id) return; const result = await campaignPerformance(props.id); if (valid()) value.value = result })
watch(() => [props.id, props.initialExpenses], () => { value.value = null; expensesOpen.value = !!props.initialExpenses; void page.load() })
const show = (n: number | null) => n === null ? '暂不可计算' : yuan(n)
function close(open: boolean) { if (!open) emit('close') }
</script>
<template>
  <USlideover :open="!!id && active" title="活动详情" description="累计收入、投入与最近收款趋势" :ui="{ content: 'sm:max-w-2xl' }" @update:open="close"><template #body><div class="promotion-campaign-detail">
    <p v-if="page.loading.value" role="status">正在读取活动数据…</p>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UButton v-if="page.error.value" label="重新加载" variant="outline" @click="page.load" />
    <div v-if="value" class="field-stack" :aria-busy="page.loading.value">
      <div><h3 class="text-xl font-semibold">{{ value.campaign.name }}</h3><p class="text-sm text-muted">{{ value.campaign.source }} · {{ value.campaign.admin_name }} · 活动累计</p></div>
      <dl class="promotion-metrics"><div><dt>真实收款</dt><dd>{{ yuan(value.income.paid_fen) }}</dd></div><div><dt>已退款</dt><dd>{{ yuan(value.income.refunded_fen) }}</dd></div><div><dt>参考奖励支出</dt><dd>{{ referenceRewardLabel(value.income) }}</dd></div><div><dt>累计投放成本</dt><dd>{{ value.spend_fen === null ? '已知小计 ' + yuan(value.known_spend_fen ?? 0) : yuan(value.spend_fen) }}</dd></div></dl>
      <UAlert v-if="value.spend_fen === null" title="此前累计成本未填写，当前仅展示已知投入；补齐累计值（无历史投入请填 0）后才能计算结余和回报率。" color="warning" /><div class="rounded-xl border border-default p-4 space-y-2"><p>扣退款、参考奖励及投放成本后：<strong>{{ show(value.remainder_fen) }}</strong></p><p>参考投放回报率：<strong>{{ value.return_bps === null ? '—' : (value.return_bps / 100).toFixed(2) + '%' }}</strong></p><p class="text-xs text-muted">回报率＝上述结余 ÷ 投放成本。尚未扣除支付渠道费、税费和其他经营成本，不代表净利润。成本未填写或奖励费用未知时不计算；零投入不计算比例。</p></div>
      <UButton label="查看推广明细" icon="i-lucide-users" @click="emit('select', id, String(value.campaign.admin_id)); emit('close')" />
      <UButton label="管理推广投入明细" variant="outline" @click="expensesOpen = !expensesOpen" />
      <ReferralExpenseLedger v-if="expensesOpen" :key="id" :campaign="id" @updated="page.load" />
      <details><summary class="cursor-pointer font-medium">最近 30 天收款趋势</summary><div class="data-scroll mt-3"><table class="data-table"><thead><tr><th>日期</th><th>收款</th><th>付费人数</th></tr></thead><tbody><tr v-for="item in value.trend" :key="item.day"><td>{{ item.day }}</td><td>{{ yuan(item.paid_fen) }}</td><td>{{ item.paying_users }}</td></tr></tbody></table></div><p v-if="!value.trend.length" class="text-sm text-muted mt-3">最近 30 天暂无真实收款</p><p class="text-xs text-muted mt-2">仅列出有收款的日期，按北京时间归集；未扣退款。</p></details>
    </div>
  </div></template></USlideover>
</template>
