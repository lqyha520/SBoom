<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import CostVoucherManager from './CostVoucherManager.vue'
import { adminIdentity, canPermission } from '../permissions'
import { useAdminPage } from '../admin-page'
import { yuan } from '../growth'
import { moneyFen } from '../settlements'
import { expenseLedger, saveExpense, type CampaignExpense, type ExpenseLedger } from '../promotion-finance'
const props = defineProps<{ campaign: string }>()
const emit = defineEmits<{ updated: [] }>()
const vouchersOpen = ref(false)
const value = ref<ExpenseLedger | null>(null), number = ref(1), start = ref(''), end = ref(''), editing = ref<CampaignExpense>(), form = ref<HTMLFormElement>()
const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10)
const day = ref(today), category = ref('广告'), amount = ref(''), evidence = ref(''), note = ref(''), sourceRef = ref(''), included = ref(false)
let requestKey = crypto.randomUUID()
const page = useAdminPage(async valid => { const result = await expenseLedger(props.campaign, start.value, end.value, number.value); if (valid()) value.value = result })
watch(number, page.load)
function search() { if (start.value && end.value && start.value > end.value) { page.error.value = '起始日期不能晚于截止日期'; return }; if (number.value === 1) void page.load(); else number.value = 1 }
async function edit(item: CampaignExpense) { editing.value = item; day.value = item.expense_date; category.value = item.category; amount.value = (item.amount_fen / 100).toFixed(2); evidence.value = item.evidence; note.value = item.note; sourceRef.value = item.source_ref || ''; included.value = !!item.included_in_baseline; await nextTick(); form.value?.scrollIntoView({ block: 'nearest' }); form.value?.querySelector('input')?.focus({ preventScroll: true }) }
function reset() { editing.value = undefined; day.value = today; category.value = '广告'; amount.value = ''; evidence.value = ''; note.value = ''; sourceRef.value = ''; included.value = false; requestKey = crypto.randomUUID() }
function save() {
  void page.act(async valid => {
    const actor = adminIdentity.value?.id
    if (!actor) throw new Error('登录信息已失效，请刷新')
    const wasEditing = !!editing.value
    await saveExpense(actor, props.campaign, { expense_date: day.value, category: category.value, amount_fen: moneyFen(amount.value), evidence: evidence.value, note: note.value, source_ref: sourceRef.value, included_in_baseline: included.value }, editing.value, requestKey)
    if (valid()) { reset(); await page.load(); if (!valid()) return; page.notice.value = wasEditing ? '投入记录已更新' : '投入记录已保存'; emit('updated') }
  })
}
function toggle(item: CampaignExpense) {
  void page.act(async valid => {
    const actor = adminIdentity.value?.id
    if (!actor) throw new Error('登录信息已失效，请刷新')
    await saveExpense(actor, props.campaign, { expense_date: item.expense_date, category: item.category, amount_fen: item.amount_fen, evidence: item.evidence, note: item.note, source_ref: item.source_ref || '', included_in_baseline: !!item.included_in_baseline }, { ...item, active: !item.active })
    if (valid()) { await page.load(); if (!valid()) return; page.notice.value = item.active ? '投入已作废，原记录保留' : '投入已恢复并计入成本'; emit('updated') }
  })
}
</script>
<template>
  <div class="field-stack promotion-expense-ledger">
    <div class="promotion-section-caption"><h3>推广投入明细台账</h3><span>{{ value?.total ?? 0 }} 条记录</span></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <p v-if="value" class="promotion-ledger-total">此前累计投入 {{ value.baseline_fen === null ? '未填写' : yuan(value.baseline_fen) }} · 全部累计 {{ value.cumulative_fen === null ? '已知小计 ' + yuan(value.known_cumulative_fen ?? 0) + '（此前累计待补齐）' : yuan(value.cumulative_fen) }}</p>
    <p class="text-xs text-muted">全部累计 = 此前累计 + 有效新增明细。已包含在此前累计中的费用请选择历史补录，补录只补齐凭据，不再次增加累计。作废历史补录不改变此前累计值。</p>
    <details v-if="value?.admin_id" class="promotion-disclosure" @toggle="vouchersOpen = ($event.target as HTMLDetailsElement).open"><summary>登记原始凭据、附件与分摊额度</summary><CostVoucherManager v-if="vouchersOpen" :owner="value.admin_id" class="mt-4" /></details>
    <form v-if="canPermission('referrals:create')" ref="form" class="field-stack promotion-expense-form" @submit.prevent="save">
      <div class="promotion-section-caption"><h4>{{ editing ? '修改投入记录' : '登记新投入' }}</h4><span v-if="editing" class="text-warning">修改中</span></div>
      <div class="promotion-form-grid">
        <UFormField label="投入日期" required><UInput v-model="day" type="date" required :max="today" :disabled="page.busy.value" /></UFormField>
        <UFormField label="投入类别"><USelect v-model="category" :items="['广告', '物料', '其他']" :disabled="page.busy.value" /></UFormField>
        <UFormField label="投入金额（元）" required><UInput v-model="amount" required inputmode="decimal" placeholder="0.00" :disabled="page.busy.value" /></UFormField>
        <UFormField label="投入凭据编号或说明" required><UInput v-model="evidence" required minlength="2" maxlength="500" placeholder="发票、账单编号或费用依据" :disabled="page.busy.value" /></UFormField>
        <UFormField label="凭据关联编号" :required="!editing"><UInput v-model="sourceRef" aria-label="凭据关联编号" :required="!editing" minlength="2" maxlength="120" placeholder="例如：发票号/广告投放；分摊用不同费用项" :disabled="page.busy.value" /></UFormField>
      </div>
      <UCheckbox v-model="included" label="历史累计内补录：此笔已包含在此前累计投入中" :disabled="page.busy.value" />
      <p v-if="included" class="text-xs text-muted">保存后累计投入不增加；有效补录合计不能超过此前累计值。部分已计入的费用请按实际分为不同费用项。</p>
      <p class="text-xs text-muted">同一凭据费用项只能有一条有效投入，换名称或换活动也不能重复登记。不同活动分摊请使用不同费用项编号，并核对分摊合计。</p>
      <UFormField label="投入备注"><UTextarea v-model="note" :rows="2" maxlength="500" placeholder="选填：投放内容或费用用途" :disabled="page.busy.value" /></UFormField>
      <div class="promotion-detail-actions"><UButton label="保存投入记录" icon="i-lucide-check" type="submit" :loading="page.busy.value" :disabled="page.busy.value || page.loading.value || !amount || evidence.trim().length < 2" /><UButton v-if="editing" label="取消修改投入" variant="ghost" :disabled="page.busy.value" @click="reset" /><UButton v-else-if="amount || evidence || note || sourceRef || included" label="清空投入草稿" variant="ghost" :disabled="page.busy.value" @click="reset" /></div>
    </form>
    <form class="promotion-finance-toolbar promotion-expense-filter" @submit.prevent="search"><UFormField label="投入起始日期"><UInput v-model="start" type="date" :max="end || today" :disabled="page.busy.value" /></UFormField><UFormField label="投入截止日期"><UInput v-model="end" type="date" :min="start || undefined" :max="today" :disabled="page.busy.value" /></UFormField><UButton label="查询投入明细" icon="i-lucide-search" variant="outline" type="submit" :loading="page.loading.value" :disabled="page.busy.value" /></form>
    <p v-if="value" class="text-sm">当前日期范围有效投入：{{ yuan(value.period_fen) }}</p>
    <div v-if="value?.items.length" class="data-scroll" role="region" aria-label="推广投入记录" tabindex="0"><table class="data-table"><thead><tr><th>日期 / 类别</th><th class="promotion-money-cell">金额</th><th>凭据 / 备注</th><th v-if="canPermission('referrals:create')">操作</th></tr></thead><tbody><tr v-for="item in value.items" :key="item.id"><td>{{ item.expense_date }}<p class="text-xs">{{ item.category }}</p><p v-if="!item.active" class="text-warning">已作废</p></td><td class="promotion-money-cell">{{ yuan(item.amount_fen) }}</td><td class="promotion-table-identity">{{ item.evidence }}<p v-if="item.source_ref" class="text-xs promotion-wrap">关联：{{ item.source_ref }}</p><p class="text-xs">{{ item.included_in_baseline ? '历史累计内补录' : '新增计入累计' }}</p><p class="text-xs whitespace-pre-wrap">{{ item.note }}</p></td><td v-if="canPermission('referrals:create')"><div class="promotion-detail-actions"><UButton label="修改投入" variant="link" :disabled="page.busy.value" @click="edit(item)" /><UButton :label="item.active ? '作废投入' : '恢复投入'" variant="link" :disabled="page.busy.value" @click="toggle(item)" /></div></td></tr></tbody></table></div>
    <p v-else class="promotion-loading">{{ page.loading.value ? '正在读取投入记录…' : '当前范围暂无投入明细' }}</p>
    <UPagination v-if="value && value.total > 20" v-model:page="number" :total="value.total" :items-per-page="20" :disabled="page.busy.value || page.loading.value" />
  </div>
</template>
