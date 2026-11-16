<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { useAdminListRoute } from '../navigation'
import { dateTime, yuan } from '../growth'
import { payoutCandidates, previewPayoutSelection, type PayoutCandidate, type PayoutSelection, cancelPayoutBatch, createPayoutBatch, downloadPayoutBatch, financeGrant, importPayoutReceipts, payoutBatch, payoutBatches, previewPayoutImport, type PayoutBatch, type PayoutBatchSummary, type PayoutImportResult, type PayoutMatch } from '../promotion-finance'
import SettlementPayment from './SettlementPayment.vue'
const props = defineProps<{ user: UserInfo }>()
const items = ref<PayoutBatchSummary[]>([]), total = ref(0), number = ref(1), available = ref<PayoutCandidate[]>([]), availableTotal = ref(0), availablePage = ref(1)
const selected = ref<string[]>([]), name = ref(''), current = ref<PayoutBatch | null>(null), content = ref(''), preview = ref<PayoutMatch | null>(null), confirmed = ref(false), result = ref<PayoutImportResult | null>(null)
const creator = ref<HTMLDetailsElement>(), panel = ref<HTMLElement>(), createOpen = ref(false), cancelOpen = ref(false), fileName = ref('')
const paymentId = ref('')
const q = ref(''), status = ref(''), requested = ref(''), detailError = ref('')
const states = { pending: '待确认', failed: '付款失败', paid: '已登记付款', cancelled: '已取消' }
const batchStates = { active: '处理中', completed: '已完成', cancelled: '已取消' }
const progress = computed(() => current.value?.items.filter(item => item.status === 'paid').length ?? 0)
let requestKey = crypto.randomUUID()
const page = useAdminPage(async valid => {
  const id = requested.value
  const [batches, statements, detail] = await Promise.allSettled([
    payoutBatches(number.value, { q: q.value, status: status.value }),
    financeGrant(props.user, 'Payout') ? payoutCandidates(availablePage.value) : Promise.resolve({ items: [], total: 0 }),
    id ? payoutBatch(id) : Promise.resolve(null),
  ])
  if (!valid()) return
  if (batches.status === 'rejected') throw batches.reason
  items.value = batches.value.items; total.value = batches.value.total
  if (statements.status === 'fulfilled') {
    available.value = statements.value.items; availableTotal.value = statements.value.total
    const lastAvailable = Math.max(1, Math.ceil(availableTotal.value / 20))
    if (availablePage.value > lastAvailable) availablePage.value = lastAvailable
  }
  else page.error.value = '待付款结算单读取失败，批次记录仍可查看，请刷新重试。'
  current.value = detail.status === 'fulfilled' ? detail.value : null
  detailError.value = detail.status === 'rejected' ? (detail.reason instanceof Error ? detail.reason.message : '付款批次详情读取失败') : ''
  const last = Math.max(1, Math.ceil(total.value / 20))
  if (number.value > last) number.value = last
}, () => { paymentId.value = '' })
const route = useAdminListRoute('financePayments', { page: number, available: availablePage, q, status, batch: requested, statement: paymentId }, page.load)
watch([number, availablePage], () => { if (!route.restoring) void page.load() })
watch(requested, () => {
  if (current.value?.id === requested.value) return
  current.value = null; content.value = ''; fileName.value = ''; result.value = null
  if (!route.restoring) void page.load()
})
function search() { if (number.value === 1) void page.load(); else number.value = 1 }
function resetFilters() { q.value = ''; status.value = ''; search() }
watch([content, () => current.value?.id, () => current.value?.revision], () => { preview.value = null; confirmed.value = false; cancelOpen.value = false })
const selection = ref<PayoutSelection | null>(null)
const selectionPage = useAdminPage(async valid => {
  selection.value = null
  if (!selected.value.length) return
  const result = await previewPayoutSelection([...selected.value])
  if (valid()) selection.value = result
})
watch(selected, () => { selection.value = null; void selectionPage.load() }, { flush: 'sync' })
function select(id: string, value: boolean | 'indeterminate') { selected.value = value === true ? [...new Set([...selected.value, id])] : selected.value.filter(item => item !== id) }
async function focusDetail() { await nextTick(); panel.value?.focus({ preventScroll: true }); panel.value?.scrollIntoView({ block: 'start' }) }
function create() {
  void page.act(async valid => {
    if (!selection.value || selection.value.blocked || selectionPage.loading.value) return
    const item = await createPayoutBatch(props.user.id, name.value, selected.value, requestKey)
    if (valid()) { selected.value = []; name.value = ''; requestKey = crypto.randomUUID(); createOpen.value = false; await page.load(); if (!valid()) return; current.value = item; requested.value = item.id; page.notice.value = '付款批次已创建，请按步骤导出清单并登记回单'; await focusDetail() }
  })
}
function inspect(item: PayoutBatchSummary) { current.value = null; requested.value = item.id; detailError.value = ''; content.value = ''; fileName.value = ''; result.value = null; void focusDetail() }
async function close() { current.value = null; requested.value = ''; detailError.value = ''; result.value = null; await nextTick(); const list = document.getElementById('payout-batch-list'); list?.focus({ preventScroll: true }); list?.scrollIntoView({ block: 'nearest' }) }
function read(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  void page.act(async valid => { try { if (file.size > 500000) throw new Error('回单 CSV 不超过 500KB'); const text = await file.text(); if (valid()) { content.value = text; fileName.value = file.name } } finally { input.value = '' } })
}
function check() { void page.act(async valid => { if (!current.value) return; const id = current.value.id, text = content.value; const result = await previewPayoutImport(id, text); if (valid() && current.value?.id === id && content.value === text) { preview.value = result; confirmed.value = false } }) }
function save() { void page.act(async valid => { if (!current.value || !confirmed.value || !preview.value) return; const value = await importPayoutReceipts(props.user.id, current.value, content.value); if (valid()) { result.value = value; confirmed.value = false; await page.load() } }) }
function paymentSaved() { selected.value = selected.value.filter(id => id !== paymentId.value); page.notice.value = '付款已登记，原结算单和月度账本已同步'; void page.load() }
function cancel() { void page.act(async valid => { if (!current.value || !cancelOpen.value) return; await cancelPayoutBatch(props.user.id, current.value); if (valid()) { cancelOpen.value = false; page.notice.value = '剩余付款批次已取消，已登记付款保留'; await page.load() } }) }
</script>
<template>
  <div class="field-stack promotion-finance-page">
    <div class="promotion-heading"><div><h2>付款办理与回单</h2><p>先核对本单收款资料，再办理单张付款或创建付款批次，完成转账后登记回单。</p></div><UButton label="刷新付款批次" icon="i-lucide-refresh-cw" variant="outline" :disabled="page.busy.value" :loading="page.loading.value" @click="page.load" /></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <form class="finance-batch-filters" aria-label="付款批次筛选" @submit.prevent="search"><UFormField label="批次名称或编号"><UInput v-model="q" maxlength="80" placeholder="搜索付款批次" :disabled="page.busy.value" /></UFormField><UFormField label="付款批次状态"><USelect v-model="status" :items="[{ value: '', label: '全部状态' }, { value: 'active', label: '处理中' }, { value: 'completed', label: '已完成' }, { value: 'cancelled', label: '已取消' }]" :disabled="page.busy.value" /></UFormField><div class="promotion-detail-actions"><UButton label="查询付款批次" type="submit" :loading="page.loading.value" :disabled="page.busy.value" /><UButton label="重置批次筛选" variant="outline" :disabled="page.busy.value" @click="resetFilters" /></div></form>
    <UAlert v-if="detailError" :title="detailError" color="error" /><UButton v-if="detailError" label="返回批次列表" variant="outline" class="self-start" @click="close" />
    <details v-if="financeGrant(user, 'Payout')" ref="creator" :open="createOpen" class="promotion-disclosure" @toggle="createOpen = creator?.open ?? false">
      <summary><span>选择待付款结算单，创建批次</span><small>{{ availableTotal }} 张待付款</small></summary>
      <form class="field-stack mt-4" @submit.prevent="create">
        <p class="text-sm text-muted">可先核对收款资料并办理单张付款，也可选择多张创建批次；已加入批次的单据请在原批次登记回单。</p>
        <UFormField label="付款批次名称" required class="promotion-short-field"><UInput v-model="name" required minlength="2" maxlength="80" placeholder="例如：十一月推广款" :disabled="page.busy.value" /></UFormField>
        <div class="data-scroll" role="region" aria-label="待付款结算单" tabindex="0"><table class="data-table"><thead><tr><th>选择</th><th>推广人 / 结算单</th><th class="promotion-money-cell">最终应付</th><th>收款账号 / 办理</th></tr></thead><tbody>
          <tr v-for="item in available" :key="item.id" :class="{ 'promotion-selected-row': selected.includes(item.id) }"><td><UCheckbox :model-value="selected.includes(item.id)" :aria-label="'加入付款批次' + item.id" :disabled="page.busy.value || !!item.payout_issues?.length || selected.length >= 200 && !selected.includes(item.id)" @update:model-value="select(item.id, $event)" /></td><td class="promotion-table-identity">{{ item.beneficiary_name }}<p class="text-xs break-all">{{ item.id }}</p></td><td class="promotion-money-cell">{{ yuan(Math.max(0, item.net_fen ?? 0)) }}</td><td>{{ item.snapshot.payee?.account || '未留存' }}<p v-for="issue in item.payout_issues" :key="issue" class="text-warning text-xs">{{ issue }}</p><UButton v-if="item.batch_id" label="查看所属批次" variant="link" @click="requested = item.batch_id" /><div><UButton label="核对资料 / 单张付款" variant="link" :disabled="page.busy.value" @click="paymentId = item.id" /></div></td></tr>
          <tr v-if="!available.length"><td colspan="4">{{ page.loading.value ? '正在读取待付款结算单…' : '暂无已审核待付款结算单，请先完成结算审核。' }}</td></tr>
        </tbody></table></div>
        <UPagination v-if="availableTotal > 20" v-model:page="availablePage" :total="availableTotal" :items-per-page="20" :disabled="page.busy.value || page.loading.value" />
        <UAlert v-if="selectionPage.error.value" :title="selectionPage.error.value" color="error" /><p v-if="selectionPage.loading.value" role="status">正在检查所选单据…</p><div v-if="selection" class="field-stack"><p>所选总金额：<strong>{{ yuan(selection.total_fen) }}</strong> · {{ selection.blocked }} 张暂不可办理</p><p v-for="item in selection.items.filter(row => row.payout_issues.length)" :key="item.id" class="text-warning">{{ item.id }}：{{ item.payout_issues.join('；') }} <UButton label="移除此单" variant="link" @click="select(item.id, false)" /></p></div><UButton v-if="selected.length" label="重新检查所选单据" variant="outline" :loading="selectionPage.loading.value" @click="selectionPage.load" /><div class="promotion-form-footer"><p>已选择 {{ selected.length }} 张，最多 200 张，可跨页选择。</p><UButton label="创建付款批次" icon="i-lucide-plus" type="submit" :loading="page.busy.value" :disabled="page.busy.value || page.loading.value || !selected.length || !selection || !!selection.blocked || selectionPage.loading.value || name.trim().length < 2" /></div>
      </form>
    </details>
    <div class="promotion-master-detail" :class="{ 'has-detail': current }">
      <section id="payout-batch-list" tabindex="-1" aria-label="付款批次列表" class="field-stack promotion-list-panel">
        <div class="promotion-section-caption"><h3>批次记录</h3><span>共 {{ total }} 个</span></div>
        <div v-if="!items.length" class="promotion-empty"><UIcon name="i-lucide-list-checks" class="promotion-empty-icon" aria-hidden="true" /><strong>{{ page.loading.value ? '正在读取付款批次…' : q || status ? '当前筛选没有付款批次' : '暂无付款批次' }}</strong><p>{{ q || status ? '调整名称或状态筛选后重试。' : financeGrant(user, 'Payout') ? '展开上方创建区，选择已审核的结算单开始处理。' : '批次创建后会显示在这里。' }}</p></div>
        <button v-for="item in items" :key="item.id" type="button" class="promotion-list-card" :class="{ selected: current?.id === item.id }" :aria-label="'查看付款批次：' + item.name" :aria-pressed="current?.id === item.id" :disabled="page.busy.value" @click="inspect(item)">
          <span class="promotion-card-top"><strong>{{ item.name }}</strong><span class="promotion-status" :class="item.status === 'completed' ? 'text-success' : item.status === 'cancelled' ? 'text-muted' : 'text-primary'">{{ batchStates[item.status] }}</span></span>
          <span class="promotion-card-bottom"><span>{{ dateTime(item.created_at) }}</span><strong>{{ yuan(item.total_fen) }} · {{ item.item_count ?? item.items?.length ?? 0 }} 张</strong></span>
        </button>
        <UPagination v-if="total > 20" v-model:page="number" :total="total" :items-per-page="20" :disabled="page.busy.value || page.loading.value" />
      </section>
      <section v-if="current" ref="panel" tabindex="-1" class="field-stack promotion-detail-panel" aria-label="付款批次详情">
        <div class="promotion-detail-heading"><div><h3>{{ current.name }}</h3><p>{{ batchStates[current.status] }} · 已登记 {{ progress }} / {{ current.items.length }} 张 · 清单总额 {{ yuan(current.total_fen) }}</p></div><UButton label="关闭批次详情" icon="i-lucide-x" variant="ghost" color="neutral" :disabled="page.busy.value" @click="close" /></div>
        <p v-if="!page.loading.value && !items.some(item => item.id === current?.id)" class="text-xs text-muted">当前打开的批次不在本页列表，调整筛选或翻页不会关闭详情。</p>
        <div class="data-scroll" role="region" aria-label="批次付款明细" tabindex="0"><table class="data-table"><thead><tr><th>结算单 / 收款人</th><th class="promotion-money-cell">最终应付</th><th>结果 / 说明</th></tr></thead><tbody><tr v-for="item in current.items" :key="item.statement_id"><td class="promotion-table-identity"><strong>{{ item.snapshot.payee?.name || item.snapshot.beneficiary_name }}</strong><p class="text-xs">{{ item.snapshot.payee?.account || '无收款账号' }}</p><p class="text-xs break-all">{{ item.statement_id }}</p></td><td class="promotion-money-cell">{{ yuan(item.snapshot.amount_fen) }}</td><td>{{ states[item.status] }}<p class="promotion-wrap">{{ item.reason || item.receipt }}</p><p v-if="item.statement_status === 'void'" class="text-warning promotion-wrap">原结算单已作废，请取消剩余批次记录。</p></td></tr></tbody></table></div>
        <template v-if="current.status === 'active' && financeGrant(user, 'Payout')">
          <ol class="promotion-steps" aria-label="付款处理步骤"><li><span>1</span>导出清单</li><li><span>2</span>完成转账</li><li><span>3</span>核对回单</li></ol>
          <div class="promotion-detail-actions"><UButton v-if="financeGrant(user, 'Payout', 'export')" label="导出待付款清单" icon="i-lucide-download" variant="outline" :disabled="page.busy.value || page.loading.value" @click="page.act(() => downloadPayoutBatch(current!.id))" /><UButton label="取消剩余付款批次" color="error" variant="ghost" :disabled="page.busy.value || page.loading.value" @click="cancelOpen = true" /></div>
          <div v-if="cancelOpen" class="promotion-review-box" role="group" aria-label="取消批次确认"><p>取消后释放未付款记录，已登记付款保留。</p><div class="promotion-detail-actions"><UButton label="确认取消剩余批次" color="error" :disabled="page.busy.value" @click="cancel" /><UButton label="继续处理" variant="outline" :disabled="page.busy.value" @click="cancelOpen = false" /></div></div>
          <details class="promotion-disclosure"><summary>回单填写说明</summary><p class="text-xs text-muted mt-3">导出含完整账号。保留原列名，结果填“成功 / 失败 / 待确认”，时间填北京时间 YYYY-MM-DD HH:mm:ss。零金额核销可留空时间，仍须填写核销凭据。</p></details>
          <UFormField label="导入银行回单 CSV"><label class="promotion-file-picker" :aria-disabled="page.busy.value"><span><UIcon name="i-lucide-upload" aria-hidden="true" />选择回单 CSV</span><small>{{ fileName ? '已读取：' + fileName : '未选择文件 · 最多 500KB' }}</small><input type="file" accept=".csv,text/csv" class="sr-only" aria-label="导入银行回单 CSV" :disabled="page.busy.value" @change="read"></label></UFormField>
          <UFormField label="回单 CSV 内容"><UTextarea v-model="content" :rows="4" maxlength="500000" placeholder="选择 CSV 文件，或将回单内容粘贴到这里" :disabled="page.busy.value" /></UFormField><UButton label="预览回单匹配" icon="i-lucide-scan-search" class="self-start" :disabled="!content.trim() || page.busy.value || page.loading.value" @click="check" />
          <div v-if="preview" class="field-stack promotion-review-box"><p>可匹配 {{ preview.matched }} 条，待处理 {{ preview.blocked }} 条。</p><p v-for="item in preview.items" :key="item.statement_id" class="text-sm break-all" :class="item.issues.length ? 'text-warning' : 'text-success'">{{ item.statement_id }}：{{ item.issues.length ? item.issues.join('；') : '匹配通过 · ' + (item.status === 'paid' ? '成功' : item.status === 'failed' ? '失败' : '待确认') }}</p><UCheckbox v-model="confirmed" label="已核对回单，仅登记匹配通过的已完成转账，异常记录保留待处理" :disabled="page.busy.value" /><UButton label="确认登记匹配回单" class="self-start" :disabled="!confirmed || !preview.matched || page.busy.value || page.loading.value" @click="save" /></div>
        </template>
        <UAlert v-if="result" :title="`回单登记：成功 ${result.paid} 条，失败 ${result.failed} 条，待确认 ${result.pending} 条，异常 ${result.blocked} 条${result.duplicate ? '（重复回单未重复记账）' : ''}`" color="info" /><p v-for="item in result?.issues" :key="item.statement_id" class="text-warning break-all">{{ item.statement_id }}：{{ item.reasons.join('；') }}</p>
      </section>
    </div>
    <SettlementPayment v-if="paymentId" :key="paymentId" :user="user" :id="paymentId" @close="paymentId = ''" @updated="paymentSaved" @batch="id => { paymentId = ''; requested = id }" />
  </div>
</template>
