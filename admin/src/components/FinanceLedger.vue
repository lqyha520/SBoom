<script setup lang="ts">
import { computed, ref } from 'vue'
import { financeLedger, createFinanceLedger, updateFinanceLedger, exportFinanceLedger, moneyFen, type FinanceLedgerEntry, type FinanceLedgerInput, type FinanceLedgerPage, voidFinanceLedger } from '../finance-ledger'
import { useAdminPage } from '../admin-page'
import { canAdmin } from '../permissions'
import { useAdminLeaveGuard } from '../navigation'
import { randomId } from '../../../shared/webcrypto'

const value = ref<FinanceLedgerPage | null>(null)
const number = ref(1), direction = ref(''), state = ref('active'), q = ref(''), start = ref(''), end = ref('')
const applied = ref<Record<string, string | number>>({})
const filters = () => ({ direction: direction.value, status: state.value, q: q.value, start_date: start.value, end_date: end.value })
const changedFilters = computed(() => JSON.stringify(applied.value) !== JSON.stringify(filters()))
const editing = ref(false), original = ref<FinanceLedgerEntry | null>(null)
const draft = ref<FinanceLedgerInput>({ entry_date: '', direction: 'expense', category: '', amount_fen: 0 })
const amount = ref(''), tax = ref('0'), initial = ref('')
const currentDraft = () => JSON.stringify([draft.value, amount.value, tax.value])
const dirty = computed(() => editing.value && initial.value !== currentDraft())
useAdminLeaveGuard(() => (!editing.value || !page.busy.value) && (!dirty.value || window.confirm('放弃尚未保存的账本修改？')))
const page = useAdminPage(async valid => {
  const params = filters()
  const result = await financeLedger({ ...params, page: number.value, page_size: 30 })
  if (valid()) { value.value = result; applied.value = params }
})
const yuan = (fen: number) => (fen / 100).toFixed(2)
function search() { number.value = 1; void page.load() }
function move(delta: number) { number.value += delta; void page.load() }
function edit(item: FinanceLedgerEntry | null) {
  if (page.busy.value) return
  if (dirty.value && !window.confirm('放弃当前修改？')) return
  original.value = item
  draft.value = item ? { identifier: item.identifier, entry_date: item.entry_date, direction: item.direction, category: item.category, amount_fen: item.amount_fen, tax_fen: item.tax_fen, counterparty: item.counterparty, reference: item.reference, note: item.note, attachment: item.attachment }
    : { identifier: randomId(), entry_date: new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10), direction: 'expense', category: '', amount_fen: 0, tax_fen: 0, counterparty: '', reference: '', note: '', attachment: '' }
  amount.value = item ? yuan(item.amount_fen) : ''; tax.value = item ? yuan(item.tax_fen || 0) : '0'
  editing.value = true; initial.value = currentDraft(); page.error.value = ''
}
function save() { void page.act(async valid => {
  const body = { ...draft.value, amount_fen: moneyFen(amount.value), tax_fen: moneyFen(tax.value || '0') }
  if (!body.category.trim() || body.amount_fen <= 0) throw new Error('请填写分类和大于零的金额')
  if (body.tax_fen > body.amount_fen) throw new Error('税额不能超过含税金额')
  if (original.value) await updateFinanceLedger(original.value.identifier!, { ...body, revision: original.value.revision })
  else await createFinanceLedger(body)
  if (valid()) { editing.value = false; page.notice.value = '账本记录已保存'; await page.load() }
}) }
function invalidate(item: FinanceLedgerEntry) {
  if (!window.confirm('作废这条账本记录？作废记录仍保留供审计。')) return
  void page.act(async valid => { await voidFinanceLedger(item); if (valid()) await page.load() })
}
function cancel() { if (!page.busy.value && (!dirty.value || window.confirm('放弃尚未保存的修改？'))) editing.value = false }
</script>
<template>
  <section class="space-y-4">
    <div class="flex flex-wrap justify-between gap-3"><div><h2 class="text-lg font-semibold">经营账本</h2><p class="text-sm text-muted">登记经营收支、税额、发票与报销凭据。汇总按当前筛选范围计算，作废记录不计入金额。</p></div><div class="flex gap-2"><UButton v-if="canAdmin('financeLedger', 'create')" label="新增收支" :disabled="page.busy.value" @click="edit(null)" /><UButton v-if="canAdmin('financeLedger', 'export')" label="导出 CSV" variant="outline" :disabled="!value || changedFilters || page.loading.value || page.busy.value" @click="page.act(() => exportFinanceLedger(applied))" /></div></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" />
    <UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="search">
      <UFormField label="方向"><USelect v-model="direction" :items="[{ label: '全部方向', value: '' }, { label: '收入', value: 'income' }, { label: '支出', value: 'expense' }]" /></UFormField>
      <UFormField label="状态"><USelect v-model="state" :items="[{ label: '有效', value: 'active' }, { label: '已作废', value: 'void' }, { label: '全部', value: '' }]" /></UFormField>
      <UFormField label="起始日期"><UInput v-model="start" type="date" /></UFormField><UFormField label="截止日期"><UInput v-model="end" type="date" /></UFormField>
      <UFormField label="搜索"><UInput v-model="q" placeholder="分类、对方或凭据" :maxlength="120" /></UFormField><UButton type="submit" label="查询" :loading="page.loading.value" />
    </form>
    <p v-if="changedFilters && value" class="text-sm text-warning">筛选已修改，点击查询后更新结果。</p>
    <div v-if="value" class="grid grid-cols-2 md:grid-cols-4 gap-3"><UCard v-for="metric in [{ label: '收入', value: value.summary.income_fen }, { label: '支出', value: value.summary.expense_fen }, { label: '净额', value: value.summary.net_fen }, { label: '税额', value: value.summary.tax_fen }]" :key="metric.label"><p class="text-xs text-muted">{{ metric.label }}</p><p class="text-xl font-semibold">¥{{ yuan(metric.value) }}</p></UCard></div>
    <UCard v-if="editing">
      <form class="space-y-3" @submit.prevent="save">
        <h3 class="font-semibold">{{ original ? '修改收支' : '新增收支' }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3"><UFormField label="日期" required><UInput :disabled="page.busy.value" v-model="draft.entry_date" type="date" required /></UFormField><UFormField label="方向" required><USelect :disabled="page.busy.value" v-model="draft.direction" :items="[{ label: '收入', value: 'income' }, { label: '支出', value: 'expense' }]" /></UFormField><UFormField label="分类" required><UInput :disabled="page.busy.value" v-model="draft.category" placeholder="如会员收入、报销、服务费" :maxlength="80" required /></UFormField><UFormField label="含税金额（元）" required><UInput :disabled="page.busy.value" v-model="amount" inputmode="decimal" required /></UFormField><UFormField label="税额（元）"><UInput :disabled="page.busy.value" v-model="tax" inputmode="decimal" /></UFormField><UFormField label="交易对方"><UInput :disabled="page.busy.value" v-model="draft.counterparty" :maxlength="160" /></UFormField><UFormField label="发票 / 报销凭据号"><UInput :disabled="page.busy.value" v-model="draft.reference" :maxlength="160" /></UFormField><UFormField label="凭据存放位置"><UInput :disabled="page.busy.value" v-model="draft.attachment" :maxlength="500" placeholder="填写凭据链接或档案位置" /></UFormField></div>
        <UFormField label="备注"><UTextarea :disabled="page.busy.value" v-model="draft.note" :maxlength="2000" class="w-full" /></UFormField>
        <div class="flex gap-2"><UButton type="submit" label="保存记录" :loading="page.busy.value" /><UButton label="取消" variant="ghost" :disabled="page.busy.value" @click="cancel" /></div>
      </form>
    </UCard>
    <div class="overflow-auto"><table class="data-table w-full"><thead><tr><th>日期</th><th>方向</th><th>分类</th><th>金额</th><th>对方</th><th>凭据</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in value?.items || []" :key="item.id"><td>{{ item.entry_date }}</td><td>{{ item.direction === 'income' ? '收入' : '支出' }}</td><td>{{ item.category }}</td><td>¥{{ yuan(item.amount_fen) }}</td><td>{{ item.counterparty || '—' }}</td><td>{{ item.reference || '—' }}</td><td>{{ item.status === 'active' ? '有效' : '已作废' }}</td><td><div v-if="item.status === 'active' && canAdmin('financeLedger', 'update')" class="flex gap-1"><UButton size="xs" label="编辑" :disabled="page.busy.value" @click="edit(item)" /><UButton size="xs" variant="ghost" label="作废" :disabled="page.busy.value" @click="invalidate(item)" /></div></td></tr><tr v-if="!value?.items.length && !page.loading.value"><td colspan="8" class="text-center text-muted py-8">暂无账本记录</td></tr></tbody></table></div>
    <div class="flex items-center justify-end gap-3"><span class="text-sm text-muted">共 {{ value?.total || 0 }} 条 · 第 {{ number }} 页</span><UButton label="上一页" :disabled="number <= 1 || page.loading.value" @click="move(-1)" /><UButton label="下一页" :disabled="!value || number * 30 >= value.total || page.loading.value" @click="move(1)" /></div>
  </section>
</template>
