<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAdminPage } from '../admin-page'
import { dateTime } from '../growth'
import { conversionPercent, getConversion, type ConversionData, type ConversionFilters } from '../referral-conversion'
const props = defineProps<{ filters: ConversionFilters }>()
const emit = defineEmits<{ select: [id: string, admin: string]; stage: [stage: string, asOf: number] }>()
const result = ref<ConversionData | null>(null), pageNumber = ref(1)
const page = useAdminPage(async valid => {
  const value = await getConversion(props.filters, pageNumber.value)
  if (!valid()) return
  const last = Math.max(1, Math.ceil(value.total / 20))
  if (pageNumber.value > last) { pageNumber.value = last; return }
  result.value = value
})
watch(() => JSON.stringify(props.filters), () => { result.value = null; if (pageNumber.value !== 1) pageNumber.value = 1; else void page.load() })
watch(pageNumber, page.load)
</script>
<template>
  <section class="conversion-panel" aria-label="推广转化漏斗">
    <div class="actions-row justify-between"><h3 class="font-semibold">注册到付费转化</h3><UButton label="刷新转化数据" icon="i-lucide-refresh-cw" color="neutral" variant="ghost" :loading="page.loading.value" @click="page.load" /></div>
    <p class="text-sm text-muted">追踪同一批注册用户的下单和付费进度，发现转化流失的位置。</p>
    <p class="text-xs text-muted">本批注册日期：{{ filters.start_date || '不限起始日期' }} 至 {{ filters.end_date || '统计当天' }}</p>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" role="alert" />
    <p v-if="page.loading.value" role="status">正在统计转化…</p>
    <template v-else-if="result && !page.error.value">
      <div class="conversion-stages">
        <button type="button" @click="emit('stage', 'all', result.as_of)"><span class="conversion-stage-label"><span class="conversion-step">01</span>注册用户<UIcon name="i-lucide-users-round" aria-hidden="true" /></span><strong>{{ result.summary.registrations }}</strong><small>{{ result.summary.not_ordered_users }} 人尚未下单</small></button>
        <button type="button" @click="emit('stage', 'not_ordered', result.as_of)"><span class="conversion-stage-label"><span class="conversion-step">02</span>未下单<UIcon name="i-lucide-user-round-search" aria-hidden="true" /></span><strong>{{ result.summary.not_ordered_users }}</strong><small>点击查看待转化用户</small></button>
        <button type="button" @click="emit('stage', 'unpaid', result.as_of)"><span class="conversion-stage-label"><span class="conversion-step">03</span>下单未付<UIcon name="i-lucide-shopping-bag" aria-hidden="true" /></span><strong>{{ result.summary.unpaid_users }}</strong><small>点击查看待付款用户</small></button>
        <button type="button" @click="emit('stage', 'paid', result.as_of)"><span class="conversion-stage-label"><span class="conversion-step">04</span>曾付费<UIcon name="i-lucide-badge-check" aria-hidden="true" /></span><strong>{{ result.summary.paying_users }}</strong><small>注册→付费 {{ conversionPercent(result.summary.pay_rate_bps) }}</small></button>
      </div>
      <p class="text-sm">点击上方阶段后，会打开对应的推广用户名单；下单→付费 {{ conversionPercent(result.summary.order_pay_rate_bps) }}</p>
      <p v-if="!result.summary.registrations" class="text-sm text-muted">这段时间暂无注册用户。可扩大注册日期范围，或清除活动筛选。</p>
      <details v-else>
        <summary class="cursor-pointer font-medium">活动转化对比 · {{ result.total }} 个来源</summary>
        <div class="data-scroll mt-3"><table class="data-table"><thead><tr><th>活动 / 归属</th><th>注册</th><th>下单</th><th>付费</th><th>注册→付费</th><th>尚未下单 / 下单未付</th><th>操作</th></tr></thead><tbody>
          <tr v-for="item in result.items" :key="item.key"><td>{{ item.name }}<p class="text-xs text-muted">{{ item.admin_name || '无归属管理员' }}{{ item.source ? ' · ' + item.source : '' }}</p></td><td>{{ item.registrations }}</td><td>{{ item.ordered_users }}</td><td>{{ item.paying_users }}</td><td>{{ conversionPercent(item.pay_rate_bps) }}</td><td>{{ item.not_ordered_users }} / {{ item.unpaid_users }}</td><td><UButton v-if="item.campaign_id" label="查看此活动" size="xs" variant="link" @click="emit('select', item.campaign_id, item.admin_id)" /><span v-else>—</span></td></tr>
        </tbody></table></div>
        <p class="text-xs text-muted mt-2 sm:hidden">左右滑动表格可查看完整活动数据。</p>
        <UPagination v-if="result.total>20" v-model:page="pageNumber" :total="result.total" :items-per-page="20" />
      </details>
      <p class="text-xs text-muted">统计于 {{ dateTime(result.as_of) }} · 财务日期口径与明细关键词不改变本漏斗。</p>
      <details class="text-xs text-muted space-y-2"><summary class="cursor-pointer">统计口径与说明</summary>
        <p>按付费人数排序；比例按人数去重，分母为零显示“—”。仅列出本批次有注册的来源，比较时请同时看样本量。“未分活动”包含管理员专属码及人工补录来源。</p>
        <p>注册日期按北京时间；已注销账号不在本批用户内，测试订单不计入。付款后退款仍计为曾付费；补录之前的其他归属订单不计入。</p>
      </details>
    </template>
  </section>
</template>
<style scoped>
.conversion-panel{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;border:1px solid var(--ui-border);border-radius:12px;padding:20px;margin-bottom:24px}
.conversion-panel>*{min-width:0}
.conversion-stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.conversion-stages button{display:grid;gap:8px;text-align:left;cursor:pointer;background:var(--ui-bg-elevated);padding:16px;border-radius:10px}
.conversion-stages strong{font-size:28px;font-weight:650;font-variant-numeric:tabular-nums}.conversion-stages small{color:var(--ui-text-muted)}
@media(max-width:600px){.conversion-panel{padding:14px}.conversion-stages{grid-template-columns:1fr}.conversion-stages button{grid-template-columns:1fr auto;align-items:center}.conversion-stages small{grid-column:1/-1}}
.conversion-stages button:hover{background:var(--ui-bg-accented)}
.conversion-stages button:focus-visible{outline:2px solid var(--ui-primary);outline-offset:3px}
</style>
