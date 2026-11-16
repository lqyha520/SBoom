<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdminPage } from '../admin-page'
import { adminIdentity, canAdmin } from '../permissions'
import { settlementAdmins } from '../settlement-operations'
import { moneyFen } from '../settlements'
import { yuan } from '../growth'
import { costVouchers, saveCostVoucher, uploadCostVoucher, downloadCostVoucher, type CostVoucher } from '../cost-vouchers'
const props = defineProps<{ owner?: number; financial?: boolean }>()
const items = ref<CostVoucher[]>([]), total = ref(0), number = ref(1), q = ref(''), selected = ref<CostVoucher | null>(null)
const people = ref<{ id: number; username: string }[]>([]), editor = ref(false), editing = ref<CostVoucher | null>(null)
const owner = ref(String(props.owner || adminIdentity.value?.id || '')), reference = ref(''), name = ref(''), amount = ref(''), evidence = ref('')
const writable = computed(() => props.financial ? canAdmin('settlementCosts', 'run') : canAdmin('referrals', 'create'))
const page = useAdminPage(async valid => {
  const result = await costVouchers(props.owner, q.value, number.value)
  if (!valid()) return
  items.value = result.items; total.value = result.total; number.value = result.page
  if (selected.value) selected.value = result.items.find(item => item.id === selected.value?.id) ?? null
  if (props.financial && !people.value.length) {
    const accounts = await settlementAdmins()
    if (valid()) people.value = accounts.items
  }
}, () => { selected.value = null; editor.value = false })
watch(number, page.load)
function search() { if (number.value === 1) void page.load(); else number.value = 1 }
function edit(item?: CostVoucher) { editing.value = item ?? null; owner.value = String(item?.admin_id || props.owner || adminIdentity.value?.id || ''); reference.value = item?.reference || ''; name.value = item?.name || ''; amount.value = item ? (item.total_fen / 100).toFixed(2) : ''; evidence.value = item?.evidence || ''; editor.value = true }
function save() { void page.act(async valid => { const value = await saveCostVoucher(adminIdentity.value!.id, { admin_id: Number(owner.value), reference: reference.value, name: name.value, total_fen: moneyFen(amount.value), evidence: evidence.value, revision: editing.value?.revision ?? 0 }, editing.value?.id); if (valid()) { editor.value = false; selected.value = value; await page.load(); page.notice.value = '凭据已保存，分摊金额由服务端统一核对' } }) }
function upload(event: Event, item: CostVoucher) { const input = event.target as HTMLInputElement, file = input.files?.[0]; if (!file) return; void page.act(async valid => { try { await uploadCostVoucher(adminIdentity.value!.id, item.id, file); if (valid()) { await page.load(); page.notice.value = '原始附件已留存' } } finally { input.value = '' } }) }
</script>
<template>
  <section class="field-stack" aria-label="原始凭据与分摊">
    <div class="promotion-heading"><div><h3>原始凭据与分摊</h3><p>先登记凭据总额，再在投入或扣费中使用“凭据号/费用项”。</p></div><UButton v-if="writable" label="登记原始凭据" :disabled="page.busy.value" @click="edit()" /></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <p class="text-xs text-muted">成本归集与奖励扣费分别不得超过凭据总额，两者不相加。作废投入释放成本额度；已付款扣费保留。尚未登记原始凭据的历史编号不参与总额校验。</p>
    <form class="actions-row" @submit.prevent="search"><UInput v-model="q" aria-label="搜索原始凭据" placeholder="凭据号或名称" maxlength="80" /><UButton label="查询原始凭据" type="submit" :loading="page.loading.value" /></form>
    <div class="data-scroll"><table class="data-table"><thead><tr><th>凭据</th><th>总额</th><th>成本已分摊 / 剩余</th><th>扣费已分摊 / 剩余</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{ item.name }}<p class="text-xs">{{ item.reference }}</p></td><td>{{ yuan(item.total_fen) }}</td><td>{{ yuan(item.expense_fen) }} / {{ yuan(item.expense_remaining_fen) }}</td><td>{{ yuan(item.deduction_fen) }} / {{ yuan(item.deduction_remaining_fen) }}</td><td><UButton label="查看凭据分摊" variant="link" @click="selected = item" /><UButton v-if="writable" label="修改凭据" variant="link" :disabled="page.busy.value" @click="edit(item)" /></td></tr><tr v-if="!items.length"><td colspan="5">{{ page.loading.value ? '正在读取…' : '暂无原始凭据' }}</td></tr></tbody></table></div>
    <UPagination v-if="total > 20" v-model:page="number" :total="total" :items-per-page="20" :disabled="page.loading.value" />
    <div v-if="selected" class="promotion-review-box field-stack"><div class="actions-row"><h4>{{ selected.name }} · {{ selected.reference }}</h4><UButton label="关闭凭据详情" variant="ghost" @click="selected = null" /></div><p class="whitespace-pre-wrap">{{ selected.evidence }}</p>
      <p v-if="!selected.files.length" class="text-warning text-sm">尚未上传原始附件</p><UButton v-for="file in selected.files" :key="file.id" :label="'下载附件：' + file.name" variant="link" @click="page.act(() => downloadCostVoucher(file))" />
      <UFormField v-if="writable" label="原始凭据附件（PNG、JPEG、PDF，每个 2MB，最多 5 个）"><input type="file" accept=".png,.jpg,.jpeg,.pdf" :disabled="page.busy.value || selected.files.length >= 5" @change="upload($event, selected)" /></UFormField>
      <p class="text-xs text-muted">共 {{ selected.count }} 项分摊，展示前 100 项；额度按全部记录计算。</p><div class="data-scroll"><table class="data-table"><thead><tr><th>用途</th><th>记录 / 费用项</th><th>金额</th></tr></thead><tbody><tr v-for="(entry, i) in selected.entries" :key="i"><td>{{ ({ expense: '成本投入', shared: '共同费用', personal: '个人费用' } as Record<string, string>)[entry.kind] }}</td><td>{{ entry.id }}<p>{{ entry.source_ref }}</p></td><td>{{ yuan(entry.amount_fen) }}</td></tr></tbody></table></div>
    </div>
    <UModal v-model:open="editor" :title="editing ? '修改原始凭据' : '登记原始凭据'" :dismissible="!page.busy.value"><template #body><form class="field-stack" @submit.prevent="save"><UAlert v-if="page.error.value" :title="page.error.value" color="error" />
      <UFormField v-if="financial" label="所属推广管理员" required><USelect v-model="owner" :items="people.map(item => ({ value: String(item.id), label: item.username }))" :disabled="!!editing || page.busy.value" /></UFormField>
      <UFormField label="原始凭据号（不含斜杠）" required><UInput v-model="reference" required minlength="2" maxlength="80" :disabled="!!editing || page.busy.value" placeholder="例如：FP202611001" /></UFormField>
      <UFormField label="凭据名称" required><UInput v-model="name" required minlength="2" maxlength="80" :disabled="page.busy.value" /></UFormField>
      <UFormField label="凭据总额（元）" required><UInput v-model="amount" required inputmode="decimal" :disabled="page.busy.value" /></UFormField>
      <UFormField label="凭据依据或修改原因" required><UTextarea v-model="evidence" required minlength="2" maxlength="1000" :disabled="page.busy.value" /></UFormField>
      <p class="text-xs text-muted">归属和编号保存后固定。总额不能低于已分摊金额，保存后可上传原始附件。</p><UButton label="保存原始凭据" type="submit" :loading="page.busy.value" /><UButton label="取消" variant="outline" :disabled="page.busy.value" @click="editor = false" />
    </form></template></UModal>
  </section>
</template>
