<script setup lang="ts">
import { ref, watch } from 'vue'
import { request } from '../api'
import { useAdminPage } from '../admin-page'
import { yuan, dateTime } from '../growth'
import type { ConversionFilters } from '../referral-conversion'
const props = defineProps<{ filters: ConversionFilters }>()
const emit = defineEmits<{ select: [id: string, admin: string] }>()
interface Metrics { cost_complete: boolean; spend_fen: number; paying_users: number; paid_fen: number; refunded_fen: number; net_fen: number; refund_rate_bps: number | null; cost_per_payer_fen: number | null }
interface Comparison { items: (Metrics & { id: string; name: string; source: string; admin_id: number; admin_name: string; previous: Metrics })[]; total: number; page: number; start_date: string; end_date: string; previous_start: string; previous_end: string; as_of: number }
const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10)
const start = ref(props.filters.start_date || new Date(Date.now() + 8 * 3600000 - 29 * 86400000).toISOString().slice(0, 10)), end = ref(props.filters.end_date || today)
const open = ref(false), number = ref(1), sort = ref('paying_users'), direction = ref('desc'), value = ref<Comparison | null>(null)
const page = useAdminPage(async valid => {
  if (!open.value) return
  if (!start.value || !end.value || start.value > end.value || end.value > today) throw new Error('请选择有效起止日期，截止日期不能晚于今天')
  const params = new URLSearchParams({ start_date: start.value, end_date: end.value, sort: sort.value, direction: direction.value, page: String(number.value) })
  for (const key of ['admin_id', 'campaign_id'] as const) if (props.filters[key]) params.set(key, props.filters[key]!)
  const result = await request<Comparison>('/api/v1/admin/referrals/comparison?' + params)
  if (valid()) { value.value = result; number.value = result.page }
})
watch(number, page.load)
watch(() => JSON.stringify(props.filters), () => { value.value = null; start.value = props.filters.start_date || start.value; end.value = props.filters.end_date || end.value; search() })
function search() { if (number.value === 1) void page.load(); else number.value = 1 }
function toggle(event: Event) { open.value = (event.target as HTMLDetailsElement).open; if (open.value) void page.load() }
const money = (n: number | null) => n === null ? '—' : yuan(n)
const rate = (n: number | null) => n === null ? '—' : (n / 100).toFixed(2) + '%'
</script>
<template>
  <details class="promotion-disclosure mb-5" @toggle="toggle"><summary><span>同周期活动对比</span><small>投入、付费与退款</small></summary>
    <div v-if="open" class="field-stack mt-4">
      <form class="promotion-finance-toolbar" @submit.prevent="search"><UFormField label="对比起始日期"><UInput v-model="start" type="date" :max="end" :disabled="page.loading.value" /></UFormField><UFormField label="对比截止日期"><UInput v-model="end" type="date" :min="start" :max="today" :disabled="page.loading.value" /></UFormField><UFormField label="排序指标"><USelect v-model="sort" :items="[{ value: 'paying_users', label: '付费人数' }, { value: 'spend', label: '已知投入' }, { value: 'cost_per_payer', label: '每位付费用户投入' }, { value: 'refund_rate', label: '订单退款比例' }, { value: 'net', label: '收款减退款' }]" :disabled="page.loading.value" /></UFormField><USelect v-model="direction" aria-label="活动排序方向" :items="[{ value: 'desc', label: '从高到低' }, { value: 'asc', label: '从低到高' }]" :disabled="page.loading.value" /><UButton label="查询活动对比" type="submit" :loading="page.loading.value" /></form>
      <UAlert v-if="page.error.value" :title="page.error.value" color="error" />
      <template v-if="value"><p class="text-sm">本期 {{ value.start_date }} 至 {{ value.end_date }} · 前期 {{ value.previous_start }} 至 {{ value.previous_end }}，天数相同。以下每格显示“本期 / 前期”。</p>
        <div class="data-scroll" role="region" aria-label="同周期活动对比表" tabindex="0"><table class="data-table"><thead><tr><th>活动 / 管理员</th><th>已知投入</th><th>付费人数</th><th>每位付费用户投入</th><th>收款减退款</th><th>订单退款比例</th><th>操作</th></tr></thead><tbody><tr v-for="item in value.items" :key="item.id"><td>{{ item.name }}<p class="text-xs">{{ item.source }} · {{ item.admin_name }}</p><p v-if="!item.cost_complete" class="text-warning text-xs">累计成本或历史投入日期未补齐</p></td><td>{{ yuan(item.spend_fen) }} / {{ yuan(item.previous.spend_fen) }}</td><td>{{ item.paying_users }} / {{ item.previous.paying_users }}<p class="text-xs">增减 {{ item.paying_users - item.previous.paying_users }} 人</p></td><td>{{ money(item.cost_per_payer_fen) }} / {{ money(item.previous.cost_per_payer_fen) }}</td><td>{{ yuan(item.net_fen) }} / {{ yuan(item.previous.net_fen) }}</td><td>{{ rate(item.refund_rate_bps) }} / {{ rate(item.previous.refund_rate_bps) }}</td><td><UButton label="查看活动用户" variant="link" @click="emit('select', item.id, String(item.admin_id))" /></td></tr><tr v-if="!value.items.length"><td colspan="7">当前范围暂无活动</td></tr></tbody></table></div>
        <UPagination v-if="value.total > 20" v-model:page="number" :total="value.total" :items-per-page="20" :disabled="page.loading.value" />
        <p class="text-xs text-muted">读取时间：{{ dateTime(value.as_of) }}。沿用概览的管理员和活动范围。收入按付款日、退款按完成日、成本按投入日计算，包含有效历史补录。收款减退款未扣奖励与经营成本。</p>
      </template>
      <details class="promotion-disclosure"><summary>比较口径</summary><p class="text-xs text-muted mt-3">每位付费用户投入＝本期已知投入÷本期真实付费人数，包含续费用户，不等于纯新客获客成本。累计成本未填写、历史累计未完整补录日期或没有付费用户时不计算。退款比例＝本期付款订单中截至查询时已退款订单数÷本期付款订单数；近期订单的观察时间更短，比较时需留意。测试订单不计入。</p></details>
    </div>
  </details>
</template>
