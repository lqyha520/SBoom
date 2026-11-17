<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CostVoucherManager from './CostVoucherManager.vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { navigateAdmin, useAdminListRoute } from '../navigation'
import { canAdmin } from '../permissions'
import { yuan, dateTime } from '../growth'
import { financeDateRange, type FinanceDatePreset } from '../finance-experience'
import { downloadFinanceExpenses, financeExpenses, type FinanceExpenseFilters, type FinanceExpense, type FinanceExpenseLedger } from '../promotion-finance'
import { settlementAdmins } from '../settlement-operations'
defineProps<{ user: UserInfo }>()
const vouchersOpen = ref(false)
const value = ref<FinanceExpenseLedger | null>(null), people = ref<{ id: number; username: string }[]>([])
const admin = ref(''), campaign = ref(''), q = ref(''), start = ref(''), end = ref(''), state = ref('all'), number = ref(1), current = ref<FinanceExpense | null>(null)
const applied = ref<FinanceExpenseFilters | null>(null), warning = ref(''), updatedAt = ref(0)
const filters = (): FinanceExpenseFilters => ({ admin_id: admin.value, campaign_id: campaign.value, q: q.value, start_date: start.value, end_date: end.value, state: state.value })
const pendingFilters = computed(() => !!applied.value && JSON.stringify(filters()) !== JSON.stringify(applied.value))
const scopeLabel = computed(() => {
  const scope = applied.value
  if (!scope) return ''
  const account = scope.admin_id ? people.value.find(item => String(item.id) === scope.admin_id)?.username || scope.admin_id : '全部管理员'
  return [account, scope.campaign_id ? '活动 ' + scope.campaign_id : '全部活动', scope.q ? '搜索“' + scope.q + '”' : '', scope.start_date || scope.end_date ? (scope.start_date || '不限起始') + ' 至 ' + (scope.end_date || '不限截止') : '全部日期', scope.state === 'void' ? '已作废记录' : scope.state === 'active' ? '有效记录' : '全部记录'].filter(Boolean).join(' · ')
})
const page = useAdminPage(async valid => {
  const scope = filters(), requestedPage = number.value
  const [ledger, accounts] = await Promise.allSettled([financeExpenses({ ...scope, page: String(requestedPage) }), settlementAdmins()])
  if (!valid()) return
  warning.value = accounts.status === 'rejected' ? '管理员选项读取失败，成本数据仍可核对；可刷新重试。' : ''
  if (accounts.status === 'fulfilled') people.value = accounts.value.items
  if (ledger.status === 'rejected') throw ledger.reason
  value.value = ledger.value; applied.value = scope; updatedAt.value = Date.now() / 1000
  const last = Math.max(1, Math.ceil(ledger.value.total / 20))
  if (number.value > last) number.value = last
}, () => { current.value = null })
const route = useAdminListRoute('financeExpenses', { admin, campaign, q, start, end, state, page: number }, page.load)
watch(number, () => { if (!route.restoring) void page.load() })
function search() { if (start.value && end.value && start.value > end.value) { page.error.value = '起始日期不能晚于截止日期'; return }; if (number.value === 1) void page.load(); else number.value = 1 }
function preset(kind: FinanceDatePreset) { const range = financeDateRange(kind); start.value = range.start; end.value = range.end; search() }
function exportLedger() { if (applied.value && !pendingFilters.value) { const scope = { ...applied.value }; void page.act(() => downloadFinanceExpenses(scope)) } }
function reset() { admin.value = ''; campaign.value = ''; q.value = ''; start.value = ''; end.value = ''; state.value = 'all'; search() }
function activity(item: FinanceExpense) { navigateAdmin('referrals', { section: 'campaigns', admin: String(item.admin_id), detail: item.campaign_id, expenses: '1' }) }
</script>
<template>
  <section class="admin-section promotion-workspace"><div class="promotion-panel field-stack promotion-finance-page">
    <div class="promotion-heading"><div><h2>活动投入汇总</h2><p>按活动和管理员核对成本，投入明细与推广活动中的记录一致。</p></div><div class="promotion-detail-actions"><UButton v-if="canAdmin('financeExpenses', 'export')" label="导出当前范围 Excel" icon="i-lucide-download" variant="outline" :disabled="!applied || pendingFilters || page.loading.value || page.busy.value" :loading="page.busy.value" @click="exportLedger" /><UButton label="刷新成本台账" icon="i-lucide-refresh-cw" variant="outline" :disabled="page.busy.value" :loading="page.loading.value" @click="page.load" /></div></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="warning" :title="warning" color="warning" />
    <details class="promotion-disclosure" @toggle="vouchersOpen = ($event.target as HTMLDetailsElement).open"><summary>原始凭据、附件与分摊额度</summary><CostVoucherManager v-if="vouchersOpen" financial class="mt-4" /></details>
    <form class="finance-expense-filters" aria-label="成本台账筛选" @submit.prevent="search">
      <UFormField label="推广管理员"><USelect v-model="admin" :items="[{ value: '', label: '全部管理员' }, ...people.map(item => ({ value: String(item.id), label: item.username }))]" :disabled="page.busy.value" /></UFormField>
      <UFormField label="活动或管理员名称"><UInput v-model="q" placeholder="搜索活动或管理员" maxlength="80" :disabled="page.busy.value" /></UFormField>
      <UFormField label="投入记录状态"><USelect v-model="state" :items="[{ value: 'all', label: '全部记录' }, { value: 'active', label: '有效投入' }, { value: 'void', label: '已作废' }]" :disabled="page.busy.value" /></UFormField>
      <div class="finance-date-fields"><UFormField label="投入起始日期"><UInput v-model="start" type="date" :max="end || undefined" :disabled="page.busy.value" /></UFormField><UFormField label="投入截止日期"><UInput v-model="end" type="date" :min="start || undefined" :disabled="page.busy.value" /></UFormField></div>
      <div class="promotion-detail-actions"><UButton label="查询成本台账" type="submit" :loading="page.loading.value" :disabled="page.busy.value" /><UButton label="重置成本筛选" variant="outline" :disabled="page.busy.value" @click="reset" /></div>
      <div class="finance-date-shortcuts" role="group" aria-label="投入日期快捷筛选"><span>快捷日期</span><UButton label="本月投入" size="sm" variant="soft" :disabled="page.loading.value || page.busy.value" @click="preset('month')" /><UButton label="上月投入" size="sm" variant="soft" :disabled="page.loading.value || page.busy.value" @click="preset('previous')" /><UButton label="全部日期" size="sm" variant="ghost" :disabled="page.loading.value || page.busy.value" @click="preset('all')" /></div>
    </form>
    <UAlert v-if="pendingFilters" title="筛选已修改，点击查询更新结果；当前金额和明细仍按上次查询范围展示" color="info" />
    <p v-if="applied" class="text-xs text-muted finance-scope-label" role="status">结果范围：{{ scopeLabel }}<span>上次读取：{{ dateTime(updatedAt) }}</span></p>
    <p v-if="campaign" class="text-sm">当前限定活动：{{ campaign }} <UButton label="查看全部活动成本" variant="link" @click="campaign = ''; search()" /></p>
    <dl v-if="value" class="promotion-metrics finance-cost-metrics"><div><dt>日期范围有效投入</dt><dd>{{ yuan(value.period_fen) }}</dd></div><div><dt>此前累计投入（已填写）</dt><dd>{{ yuan(value.baseline_fen) }}</dd></div><div><dt>全部累计投入（已知小计）</dt><dd>{{ yuan(value.cumulative_fen) }}</dd></div></dl>
    <p class="text-xs text-muted">日期范围金额包括有效历史补录；历史补录不再次叠加到全部累计。此前累计值没有发生日期，累计金额按所选管理员、活动和名称范围计算，不受日期及作废状态筛选影响。</p><UAlert v-if="value?.unknown_campaigns" :title="`${value.unknown_campaigns} 个活动尚未填写此前累计投入，累计金额为已知小计`" color="warning" />
    <div class="data-scroll" role="region" aria-label="财务成本台账，可横向滚动" tabindex="0"><table class="data-table"><thead><tr><th>活动 / 管理员</th><th>日期 / 类别</th><th class="promotion-money-cell">投入金额</th><th>凭据 / 状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in value?.items" :key="item.id"><td class="promotion-table-identity"><strong>{{ item.campaign_name }}</strong><p>{{ item.admin_name }}</p></td><td>{{ item.expense_date }}<p class="text-xs">{{ item.category }}</p></td><td class="promotion-money-cell">{{ yuan(item.amount_fen) }}</td><td class="promotion-table-identity">{{ item.evidence }}<p v-if="item.source_ref" class="text-xs promotion-wrap">关联：{{ item.source_ref }}</p><p class="text-xs">{{ item.included_in_baseline ? '历史累计内补录' : '新增计入累计' }}</p><p :class="item.active ? 'text-success' : 'text-warning'">{{ item.active ? '有效投入' : '已作废' }}</p></td><td><div class="promotion-detail-actions"><UButton label="查看投入凭据" variant="outline" @click="current = item" /><UButton v-if="canAdmin('referrals')" label="查看活动投入" variant="link" @click="activity(item)" /></div></td></tr><tr v-if="!value?.items.length"><td colspan="5">{{ page.loading.value ? '正在读取成本台账…' : page.error.value && !value ? '成本台账暂不可用，请刷新重试' : '当前范围没有投入明细' }}</td></tr></tbody></table></div>
    <div class="table-footer"><span>共 {{ value?.total ?? 0 }} 条记录</span><UPagination v-if="value && value.total > 20" v-model:page="number" :total="value.total" :items-per-page="20" :disabled="page.loading.value" /></div>
    <UModal :open="!!current" title="投入凭据与记录" @update:open="current = null"><template #body><div v-if="current" class="field-stack text-sm"><p><strong>{{ current.campaign_name }}</strong> · {{ current.admin_name }}</p><p>{{ current.expense_date }} · {{ current.category }} · {{ yuan(current.amount_fen) }}</p><p class="whitespace-pre-wrap promotion-wrap">凭据：{{ current.evidence }}</p><p class="promotion-wrap">关联编号：{{ current.source_ref || '历史记录未填写' }}</p><p>累计处理：{{ current.included_in_baseline ? '历史累计内补录，不重复增加' : '新增计入累计' }}</p><p class="whitespace-pre-wrap promotion-wrap">备注：{{ current.note || '未填写' }}</p><p>记录版本 {{ current.revision }} · {{ current.active ? '有效投入' : '已作废，保留原记录' }}</p><p class="text-xs text-muted">首次登记：{{ dateTime(current.created_at) }}</p><UButton v-if="canAdmin('referrals')" label="前往原活动核对投入" @click="activity(current)" /></div></template></UModal>
  </div></section>
</template>
