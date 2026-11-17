<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdminPage } from '../admin-page'
import { dateTime, yuan } from '../growth'
import { referralQuality, type QualityRow } from '../promotion-finance'
import type { ConversionFilters } from '../referral-conversion'
const props = defineProps<{ filters: ConversionFilters }>()
const open = ref(false), items = ref<QualityRow[]>([]), total = ref(0), number = ref(1), asOf = ref(0)
const observationWindow = ref('all')
const visibleItems = computed(() => items.value.filter(item => observationWindow.value === 'all' || String(item.days) === observationWindow.value))
const page = useAdminPage(async valid => { if (!open.value) return; const result = await referralQuality(props.filters, number.value); if (valid()) { items.value = result.items; total.value = result.total; asOf.value = result.as_of } })
watch(() => JSON.stringify(props.filters), () => { items.value = []; if (number.value !== 1) number.value = 1; else void page.load() })
watch(number, page.load)
function toggle(event: Event) { const next = (event.target as HTMLDetailsElement).open; if (next !== open.value) { open.value = next; if (next) void page.load() } }
const rate = (value: number | null) => value === null ? '—' : (value / 100).toFixed(2) + '%'
</script>
<template>
  <details class="promotion-disclosure mb-5" @toggle="toggle"><summary><span>注册后 30 / 60 / 90 天用户质量</span><small>按注册批次观察</small></summary>
    <div v-if="open" class="field-stack mt-4">
      <div class="promotion-finance-toolbar"><UFormField label="观察窗口"><USelect v-model="observationWindow" :items="[{ value: 'all', label: '对比全部窗口' }, { value: '30', label: '30 天窗口' }, { value: '60', label: '60 天窗口' }, { value: '90', label: '90 天窗口' }]" :disabled="page.loading.value" /></UFormField><UButton label="刷新用户质量" icon="i-lucide-refresh-cw" variant="outline" :loading="page.loading.value" @click="page.load" /></div>
      <p class="text-xs text-muted">沿用管理员、活动和注册日期筛选。已观察人数用于计算比例，未满窗口人数单独展示；虚拟支付测试订单不计入。</p>
      <UAlert v-if="page.error.value" :title="page.error.value" color="error" />
      <div class="data-scroll" role="region" aria-label="用户质量统计表，可横向滚动" tabindex="0"><table class="data-table"><thead><tr><th>活动 / 管理员</th><th>窗口</th><th>已观察 / 未满窗口</th><th>付费人数 / 转化率</th><th>续费人数 / 续费率</th><th>退款人数</th><th class="promotion-money-cell">净收款 / 人均</th></tr></thead><tbody><tr v-for="item in visibleItems" :key="item.group_key + ':' + item.days"><td class="promotion-table-identity">{{ item.campaign_name }}<p class="text-xs">{{ item.admin_name || '无归属管理员' }}</p></td><td>{{ item.days }} 天</td><td>{{ item.observed_users }} / {{ item.waiting_users }}</td><td>{{ item.paying_users }} / {{ rate(item.pay_rate_bps) }}</td><td>{{ item.renewing_users }} / {{ rate(item.renewal_rate_bps) }}</td><td>{{ item.refunded_users }}</td><td class="promotion-money-cell">{{ yuan(item.net_fen) }} / {{ item.value_per_user_fen === null ? '—' : yuan(item.value_per_user_fen) }}</td></tr><tr v-if="!visibleItems.length"><td colspan="7">{{ page.loading.value ? '正在统计…' : '暂无匹配的注册用户' }}</td></tr></tbody></table></div>
      <UPagination v-if="total > 20" v-model:page="number" :total="total" :items-per-page="20" :disabled="page.loading.value" />
      <p v-if="asOf" class="text-xs text-muted">统计时点：{{ dateTime(asOf) }}。可横向滚动查看完整指标；人均净收款仅扣退款，未扣奖励、手续费与经营成本。</p>
      <details class="promotion-disclosure"><summary>付费、续费与退款口径</summary><p class="text-xs text-muted mt-3">续费率＝窗口内至少两次成功付款人数 ÷ 付费人数；退款后的付款仍计入付款经历，退款金额另扣除。付款和退款只计入各自观察窗口内发生的记录。</p></details>
    </div>
  </details>
</template>
