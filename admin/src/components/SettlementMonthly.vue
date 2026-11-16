<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { useAdminListRoute, type AdminTab } from '../navigation'
import { dateTime, yuan } from '../growth'
import { archiveMonthly, downloadMonthly, financeGrant, financeUser, ledgerLabels, monthlyReport, type MonthlyReport } from '../promotion-finance'
import { canPermission } from '../permissions'
import { settlementAdmins } from '../settlement-operations'
const props = defineProps<{ user: UserInfo; routeTab?: AdminTab }>()
const admin = ref(String(props.user.id)), month = ref(new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 7))
const filterKey = 'lc-monthly-scope:' + props.user.id + (financeUser(props.user) ? ':finance' : ':personal')
try {
  const saved = JSON.parse(sessionStorage.getItem(filterKey) || 'null')
  if (saved && /^\d{4}-\d{2}$/.test(saved.month) && /^\d+$/.test(saved.admin)) {
    month.value = saved.month; if (financeUser(props.user)) admin.value = saved.admin
  }
} catch { /* 筛选备份不可用时使用当前月份。 */ }
const people = ref<{ id: number; username: string }[]>([]), value = ref<MonthlyReport | null>(null), confirmed = ref(false), visibleRows = ref(100)
const ended = computed(() => month.value < new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 7))
const page = useAdminPage(async valid => {
  confirmed.value = false
  const [report, accounts] = await Promise.all([monthlyReport(admin.value, month.value), financeUser(props.user) ? settlementAdmins() : Promise.resolve({ items: [] })])
  if (valid()) { value.value = report; people.value = accounts.items; confirmed.value = false; visibleRows.value = 100 }
})
const route = props.routeTab ? useAdminListRoute(props.routeTab, { admin, month }, page.load) : null
watch([admin, month], () => { value.value = null; confirmed.value = false; try { sessionStorage.setItem(filterKey, JSON.stringify({ admin: admin.value, month: month.value })) } catch { /* 筛选仍可使用。 */ }; if (!route?.restoring) void page.load() })
function archive() {
  const report = value.value
  if (!report || !confirmed.value || !ended.value || page.loading.value) return
  void page.act(async valid => {
    confirmed.value = false
    const saved = await archiveMonthly(props.user.id, report)
    if (valid()) { value.value = saved; page.notice.value = '月度对账单已留档，后续更正将保留原结果' }
  })
}
</script>
<template>
  <div class="field-stack promotion-finance-page">
    <div class="promotion-heading"><div><h2>月度对账单</h2><p>先核对期初与期末余额，再查看变动明细。统计按北京时间归集。</p></div><UButton v-if="value && canPermission('settlements:export')" label="下载月度对账单" icon="i-lucide-download" variant="outline" :disabled="page.busy.value || page.loading.value" @click="page.act(() => downloadMonthly(admin, month))" /></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" />
    <UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <div class="promotion-finance-toolbar"><UFormField v-if="financeUser(user)" label="推广人"><USelect v-model="admin" :items="people.map(item => ({ value: String(item.id), label: item.username }))" aria-label="月度对账推广人" :disabled="page.busy.value" /></UFormField><UFormField label="对账月份"><UInput v-model="month" type="month" :disabled="page.busy.value" /></UFormField><UButton label="刷新月度对账" icon="i-lucide-refresh-cw" variant="outline" :disabled="page.busy.value" :loading="page.loading.value" @click="page.load" /></div>
    <p v-if="page.loading.value" role="status" class="promotion-loading">正在读取月度账本…</p>
    <template v-if="value"><div class="promotion-report-caption"><p>{{ value.admin_name }} · {{ value.month }} · {{ value.archive_id ? '已留档（原结果保留）' : '实时预览' }}</p><span v-if="value.archive_id" class="promotion-status text-success"><UIcon name="i-lucide-lock-keyhole" />已锁定版本</span><span v-else class="text-muted text-xs">未审核奖励不计入余额</span></div>
      <dl class="promotion-metrics promotion-balance-metrics"><div><dt>期初核定余额</dt><dd>{{ yuan(value.opening_fen) }}</dd></div><div><dt>核定税前奖励</dt><dd>{{ yuan(value.totals.reward || 0) }}</dd></div><div><dt>本月已付款</dt><dd>{{ yuan(-(value.totals.payment || 0)) }}</dd></div><div class="promotion-balance-total"><dt>期末核定余额</dt><dd>{{ yuan(value.closing_fen) }}</dd></div></dl>
      <p v-if="value.closing_fen < 0" class="text-warning">负余额为后续待抵扣金额。</p>
      <div v-if="financeGrant(user, 'Review') && !value.archive_id" class="promotion-review-box"><UCheckbox v-model="confirmed" label="已核对本月余额与明细，确认保留此版本" :disabled="!ended || page.busy.value || page.loading.value" /><div class="promotion-form-footer"><p>{{ ended ? '留档后保留此版本；迟到记录和更正归入后续未留档月份。' : '本月尚未结束，可下载实时对账单，在下月确认留档。' }}</p><UButton label="留档月度对账单" icon="i-lucide-archive" :disabled="!ended || !confirmed || page.busy.value || page.loading.value" :loading="page.busy.value" @click="archive" /></div></div>
      <details class="promotion-disclosure"><summary><span>余额变动明细</span><small>{{ value.items.length }} 条</small></summary><div class="field-stack mt-4"><dl class="promotion-breakdown"><div v-for="(label, kind) in ledgerLabels" :key="kind"><dt>{{ label }}</dt><dd>{{ yuan(value.totals[kind] || 0) }}</dd></div></dl>
      <div class="data-scroll"><table class="data-table"><thead><tr><th>入账时间</th><th>项目</th><th>余额变动</th><th>结算单 / 来源</th></tr></thead><tbody><tr v-for="item in value.items.slice(0, visibleRows)" :key="item.source"><td>{{ dateTime(item.occurred_at) }}<p v-if="item.original_at && item.original_at !== item.occurred_at" class="text-xs text-muted">原发生时间：{{ dateTime(item.original_at) }}</p></td><td>{{ ledgerLabels[item.kind] }}</td><td>{{ yuan(item.amount_fen) }}</td><td class="break-all">{{ item.statement_id || item.source }}</td></tr><tr v-if="!value.items.length"><td colspan="4">此月没有核定余额变动</td></tr></tbody></table></div>
      <UButton v-if="value.items.length > visibleRows" :label="`显示更多明细（共 ${value.items.length} 条）`" variant="outline" class="self-start" @click="visibleRows += 100" />
      </div></details>
    </template>
  </div>
</template>
