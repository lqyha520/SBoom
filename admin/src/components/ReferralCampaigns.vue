<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useAdminRefresh } from '../admin-page'
import { useBeforeUnload } from '../unsaved'
import { readBudgetDraft, storeBudgetDraft, type MonthlyBudgetDraft } from '../promotion-budget-draft'
import type { UserInfo } from '../api'
import { referenceRewardLabel, type Promoter } from '../referrals'
import { canPermission } from '../permissions'
import { yuan } from '../growth'
import { moneyFen } from '../settlements'
import { campaigns, createCampaign, updateCampaign, downloadCampaign, loadBudget, saveBudget, type Campaign, type Budget } from '../referral-operations'
import PromotionActions from './PromotionActions.vue'
import PromotionStatus from './PromotionStatus.vue'
import ReferralMaterials from './ReferralMaterials.vue'
import ReferralCampaignDetail from './ReferralCampaignDetail.vue'
const props = defineProps<{ user: UserInfo; accounts: Promoter[]; requested?: string; requestedOwner?: string; requestedExpenses?: boolean }>()
const emit = defineEmits<{ select: [id: string, admin: string]; 'close-detail': [] }>()
const editorOpen = ref(false)
const admin = ref(String(props.user.id)), items = ref<Campaign[]>([]), busy = ref(false), error = ref(''), notice = ref('')
const name = ref(''), source = ref('微信群'), budget = ref(''), monthlyValue = ref<Budget | null>(null), version = ref('release'), editing = ref<Campaign | null>(null)
const monthlyDrafts = reactive(new Map<string, MonthlyBudgetDraft & { restored?: boolean }>())
const restoredOwners = new Set<string>(), draftStorageError = ref('')
const monthly = computed({ get: () => monthlyDrafts.get(admin.value)?.value ?? '', set: value => {
  const draft = monthlyDrafts.get(admin.value)
  if (draft) draft.value = value
} })
const monthlyDirty = computed(() => { const draft = monthlyDrafts.get(admin.value); return !!draft && draft.value !== draft.saved })
const monthlyConflict = computed(() => monthlyDirty.value && monthlyDrafts.get(admin.value)?.revision !== monthlyValue.value?.revision)
watch(monthlyDrafts, () => {
  if (!props.user.is_super_admin) return
  try { for (const [owner, draft] of monthlyDrafts) storeBudgetDraft(props.user.id, owner, draft); draftStorageError.value = '' }
  catch { draftStorageError.value = '预算草稿暂无法保存在本标签页，刷新前请先保存到后台或复制输入。' }
}, { deep: true, flush: 'sync' })
useBeforeUnload(computed(() => [...monthlyDrafts.values()].some(draft => draft.value !== draft.saved)))
const query = ref(''), channel = ref(''), state = ref('active'), pageNumber = ref(1), total = ref(0)
const spend = ref(''), landingKind = ref('home'), landingId = ref('')
const toggleTarget = ref<Campaign | null>(null)
const materialTarget = ref<Campaign | null>(null), detailTarget = ref('')
const budgetProgress = computed(() => monthlyValue.value?.budget_fen ? Math.min(100, monthlyValue.value.used_fen / monthlyValue.value.budget_fen * 100) : null)
function moreActions(item: Campaign) {
  return [
    ...(item.active ? [{ label: '复制活动路径', icon: 'i-lucide-copy', onSelect: () => copy(item) }] : []),
    ...(canPermission('referrals:export') && item.active ? [{ label: '下载活动码', icon: 'i-lucide-download', onSelect: () => run(() => downloadCampaign(props.user.id, item.id, version.value)) }] : []),
    ...(canPermission('referrals:create') ? [
      { label: '修改活动', icon: 'i-lucide-pencil', onSelect: () => edit(item) },
      { label: item.active ? '停用活动码' : '启用活动码', icon: item.active ? 'i-lucide-pause' : 'i-lucide-play', ...(item.active ? { color: 'error' as const } : {}), onSelect: () => { toggleTarget.value = item } },
    ] : []),
  ]
}
async function run(operation: () => Promise<unknown>) { if (busy.value) return; busy.value = true; error.value = ''; try { await operation() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败' } finally { busy.value = false } }
async function load() {
  const owner = admin.value
  const [list, value] = await Promise.all([campaigns(Number(owner), { q: query.value.trim(), source: channel.value.trim(), state: state.value, page: String(pageNumber.value) }), loadBudget(Number(owner))])
  if (owner !== admin.value) return
  items.value = list.items; total.value = list.total ?? list.items.length; monthlyValue.value = value
  if (props.user.is_super_admin && !restoredOwners.has(owner)) {
    restoredOwners.add(owner)
    try { const draft = readBudgetDraft(props.user.id, owner); if (draft) monthlyDrafts.set(owner, { ...draft, restored: true }) }
    catch { draftStorageError.value = '无法读取本标签页的预算草稿，请核对后台预算后继续编辑。' }
  }
  const draft = monthlyDrafts.get(owner)
  if (!draft || draft.value === draft.saved) {
    const text = value.budget_fen === null ? '' : (value.budget_fen / 100).toFixed(2)
    monthlyDrafts.set(owner, { value: text, saved: text, revision: value.revision })
  }
  const last = Math.max(1, Math.ceil(total.value / 20))
  if (pageNumber.value > last) { pageNumber.value = last; await load() }
}
function search() { if (busy.value) return; pageNumber.value = 1; void run(load) }
function pageChanged(value: number) { pageNumber.value = value; void run(load) }
function resetSearch() { query.value = ''; channel.value = ''; state.value = 'all'; search() }
function saveMonthly() { void run(async () => {
  const owner = admin.value, draft = monthlyDrafts.get(owner)
  if (!draft || !monthlyValue.value) return
  monthlyValue.value = await saveBudget(props.user.id, Number(owner), { ...monthlyValue.value, revision: draft.revision }, draft.value.trim() ? moneyFen(draft.value) : null)
  draft.saved = draft.value; draft.revision = monthlyValue.value.revision; draft.restored = false
  notice.value = '月度预算预警已保存'
}) }
function reloadMonthly() {
  if (monthlyDirty.value && !window.confirm('重新载入会放弃当前管理员尚未保存的月度预算，是否继续？')) return
  try { storeBudgetDraft(props.user.id, admin.value) }
  catch { draftStorageError.value = '无法清除本标签页的预算草稿，再次刷新时请核对后台版本。' }
  monthlyDrafts.delete(admin.value); void run(load)
}
function selectDetail(id: string, owner: string) { emit('select', id, owner) }
function edit(item: Campaign) { editing.value = item; spend.value = item.spend_fen == null ? '' : (item.spend_fen / 100).toFixed(2); landingKind.value = item.landing_kind || 'home'; landingId.value = item.landing_id || ''; name.value = item.name; source.value = item.source; budget.value = item.budget_fen === null ? '' : (item.budget_fen / 100).toFixed(2); editorOpen.value = true }
function reset() { editing.value = null; name.value = ''; source.value = '微信群'; budget.value = ''; spend.value = ''; landingKind.value = 'home'; landingId.value = '' }
function copy(item: Campaign) { void run(async () => { await navigator.clipboard.writeText(item.path); notice.value = '活动路径已复制' }) }
function save() { void run(async () => { const value = { admin_id: Number(admin.value), name: name.value, source: source.value, budget_fen: budget.value.trim() ? moneyFen(budget.value) : null, spend_fen: spend.value.trim() ? moneyFen(spend.value) : null, landing_kind: landingKind.value, landing_id: landingKind.value === 'home' ? '' : landingId.value.trim() }; if (editing.value) await updateCampaign(props.user.id, editing.value, { ...value, active: editing.value.active }); else await createCampaign(props.user.id, value); reset(); editorOpen.value = false; await load(); notice.value = '活动已保存，已有用户与订单保留原来源快照' }) }
function toggle(item: Campaign) { void run(async () => { await updateCampaign(props.user.id, item, { name: item.name, source: item.source, budget_fen: item.budget_fen, active: !item.active }); toggleTarget.value = null; await load(); notice.value = item.active ? '活动码已停用，已有用户和订单不受影响' : '活动码已启用，可以继续分享' }) }
watch(admin, () => { pageNumber.value = 1; detailTarget.value = ''; materialTarget.value = null; reset(); void run(load) })
watch(() => [props.requested, props.requestedOwner], async () => {
  if (!props.requested) return
  if (props.requestedOwner && /^\d+$/.test(props.requestedOwner)) admin.value = props.requestedOwner
  await nextTick()
  detailTarget.value = props.requested
}, { immediate: true })
useAdminRefresh(() => { void run(load) })
</script>
<template>
  <section aria-label="推广活动">
    <div class="promotion-heading"><div><h2>推广活动</h2><p>为不同渠道建立活动，单独追踪带来的用户和收入。列表显示活动累计表现。</p></div><div class="actions-row"><USelect v-if="user.is_super_admin" v-model="admin" size="md" :items="accounts.map(item => ({ value: String(item.id), label: item.username }))" aria-label="活动所属管理员" :disabled="busy" /><UButton v-if="canPermission('referrals:create')" label="新建推广活动" icon="i-lucide-plus" size="md" :disabled="busy" @click="reset(); editorOpen = true" /></div></div>
    <form class="promotion-record-toolbar" aria-label="活动筛选" @submit.prevent="search">
      <UInput v-model="query" placeholder="搜索活动名称" aria-label="活动名称筛选" maxlength="80" :disabled="busy" icon="i-lucide-search" />
      <UInput v-model="channel" placeholder="来源渠道" aria-label="活动渠道筛选" maxlength="80" :disabled="busy" />
      <USelect v-model="state" aria-label="活动状态筛选" :disabled="busy" :items="[{ value: 'active', label: '启用中' }, { value: 'inactive', label: '已停用' }, { value: 'all', label: '全部活动' }]" @update:model-value="search" />
      <UButton label="筛选活动" type="submit" :loading="busy" /><UButton label="查看全部活动" color="neutral" variant="ghost" :disabled="busy" @click="resetSearch" />
    </form>
    <div class="field-stack">
    <UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" />
    <UAlert v-if="draftStorageError" :title="draftStorageError" color="warning" />
    <p v-if="monthlyDrafts.get(admin)?.restored && monthlyDirty" role="status" class="text-sm text-muted">已恢复本标签页尚未保存的预算草稿，保存后生效。</p>
    <UAlert v-if="monthlyConflict" title="后台预算已更新，当前草稿保留原版本。请复制输入并重新载入预算后核对修改。" color="warning" />
    <div v-if="monthlyValue" class="promotion-budget space-y-3 text-sm"><p>本月参考奖励支出 <strong>{{ referenceRewardLabel({ reward_reference_fen: monthlyValue.used_fen, reward_unknown: monthlyValue.unknown, reward_known: monthlyValue.reward_known }) }}</strong> · 预算 {{ monthlyValue.budget_fen === null ? '未设置' : yuan(monthlyValue.budget_fen) }}</p><UAlert v-if="monthlyValue.reached" title="管理员本月奖励预算已达到，请检查推广投入" color="warning" /><div v-if="budgetProgress !== null" class="promotion-budget-track" role="progressbar" aria-label="本月预算使用比例" :aria-valuenow="Math.round(budgetProgress)" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: budgetProgress + '%' }" /></div><details><summary class="cursor-pointer text-muted">预算设置与说明</summary><div class="space-y-3 mt-4"><p class="text-xs text-muted">管理员预算按北京时间每月付款产生的奖励预警，活动预算按累计参考税前奖励预警；预算仅提醒，不截断已经产生的奖励。</p><form v-if="user.is_super_admin" class="actions-row" @submit.prevent="saveMonthly"><UFormField label="管理员月度预算（元，留空关闭预警）"><UInput v-model="monthly" inputmode="decimal" maxlength="80" :disabled="busy" /></UFormField><UButton label="保存月度预算" type="submit" :disabled="busy" /><UButton label="重新载入预算" variant="ghost" :disabled="busy" @click="reloadMonthly" /><span v-if="monthlyDirty" class="text-warning">预算修改尚未保存，筛选和翻页会保留输入</span></form></div></details></div>
    <UModal v-if="canPermission('referrals:create')" v-model:open="editorOpen" :title="editing ? '修改推广活动' : '新建推广活动'" :dismissible="!busy"><template #body><form class="field-stack" @submit.prevent="save"><UAlert v-if="error" :title="error" color="error" /><p class="text-sm text-muted">活动推广码归属当前管理员，已有用户与订单的来源保持不变。</p><UFormField label="活动名称" required><UInput v-model="name" autofocus size="md" required minlength="2" maxlength="80" :disabled="busy" class="w-full" /></UFormField><UFormField label="来源标签" required><UInput v-model="source" size="md" required minlength="2" maxlength="80" :disabled="busy" class="w-full" /></UFormField><UFormField label="活动累计预算（元，留空关闭预警）"><UInput v-model="budget" size="md" inputmode="decimal" :disabled="busy" class="w-full" /></UFormField><UFormField label="此前累计投放成本（元，未填写表示未知）"><UInput v-model="spend" inputmode="decimal" :disabled="busy" class="w-full" /></UFormField><p class="text-xs text-muted">填写采用明细台账前的历史累计成本。新增投入另外累加；已包含在此累计值中的费用可按“历史累计内补录”补齐凭据，不重复累加。累计值不能低于有效历史补录合计，不包含推广奖励。</p>
      <UFormField label="扫码落地内容"><USelect v-model="landingKind" :disabled="busy" :items="[{ value: 'home', label: '小程序首页' }, { value: 'topic', label: '专题合集' }, { value: 'paper', label: '资料详情' }]" class="w-full" /></UFormField>
      <UFormField v-if="landingKind !== 'home'" label="内容编号" required><UInput v-model="landingId" required maxlength="80" pattern="[a-zA-Z0-9_-]+" :disabled="busy" class="w-full" /></UFormField><p class="text-xs text-muted">内容编号可从小程序分享路径的 id 参数取得。仅支持公开内容；需使用支持活动落地的新版本小程序。</p>
      <div class="promotion-dialog-actions"><UButton :label="editing ? '保存活动修改' : '创建活动推广码'" size="md" icon="i-lucide-check" type="submit" :disabled="busy" /><UButton label="取消" color="neutral" size="md" variant="outline" :disabled="busy" @click="editorOpen = false" /></div></form></template></UModal>
    <details v-if="canPermission('referrals:export') && items.length" class="text-sm"><summary class="cursor-pointer text-muted">推广码下载选项</summary><USelect v-model="version" :items="[{ value: 'release', label: '正式版' }, { value: 'trial', label: '体验版' }, { value: 'develop', label: '开发版' }]" aria-label="活动码版本" :disabled="busy" class="mt-3" /></details>
    <div v-if="items.length" class="data-scroll" :aria-busy="busy"><table class="data-table promotion-campaign-table"><thead><tr><th>活动 / 来源</th><th>推广表现</th><th>参考奖励 / 预算</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id">
      <td class="record-identity"><strong>{{ item.name }} · {{ item.source }}</strong><div class="mt-2"><PromotionStatus :status="item.active ? 'enabled' : 'disabled'" :label="item.active ? '启用中' : '已停用新注册入口'" /></div></td>
      <td><div class="promotion-inline-stats"><span><strong>{{ item.registrations }}</strong> 注册</span><span><strong>{{ item.paying_users }}</strong> 付费</span></div></td>
      <td><strong class="tabular-nums">{{ referenceRewardLabel({ reward_reference_fen: item.reward_fen, reward_unknown: item.unknown, reward_known: item.reward_known }) }}</strong><div class="text-xs text-muted">预算 {{ item.budget_fen === null ? '未设置' : yuan(item.budget_fen) }}</div><p v-if="item.budget_reached" class="text-warning text-xs">已达到预算</p></td>
      <td><div class="promotion-row-actions"><UButton label="活动详情" variant="soft" @click="detailTarget = item.id" /><UButton v-if="canPermission('referrals:export') && item.active" label="推广素材" icon="i-lucide-image" color="neutral" variant="outline" :disabled="busy" @click="materialTarget = item" /><PromotionActions :items="moreActions(item)" :disabled="busy" /></div></td>
    </tr></tbody></table></div>
    <div v-else-if="!busy" class="promotion-empty"><UIcon name="i-lucide-megaphone" class="promotion-empty-icon" aria-hidden="true" /><strong>当前筛选下暂无活动</strong><p>可调整名称、渠道或状态，也可以创建新的推广活动。</p><p class="text-xs">现有管理员专属推广码继续可用。</p><UButton v-if="canPermission('referrals:create')" label="创建第一个活动" icon="i-lucide-plus" variant="soft" size="md" @click="reset(); editorOpen = true" /></div>
    <div v-if="total" class="table-footer"><span>共 {{ total }} 个活动 · 每页 20 个</span><UPagination :page="pageNumber" :total="total" :items-per-page="20" :disabled="busy" @update:page="pageChanged" /></div>
    <UModal :open="!!toggleTarget" :title="toggleTarget?.active ? '停用活动推广码' : '启用活动推广码'" :dismissible="!busy" @update:open="value => { if (!value) toggleTarget = null }"><template #body><div v-if="toggleTarget" class="field-stack"><UAlert v-if="error" :title="error" color="error" /><p class="font-semibold">{{ toggleTarget.name }}</p><p class="text-sm text-muted">{{ toggleTarget.active ? '停用后，此活动码将不再接受新注册。已有用户的归属、订单和奖励保持不变。' : '启用后，可继续分享该活动码并接收新注册用户。' }}</p><div class="promotion-dialog-actions"><UButton :label="toggleTarget.active ? '确认停用' : '确认启用'" :color="toggleTarget.active ? 'error' : 'primary'" size="md" :loading="busy" @click="toggle(toggleTarget)" /><UButton label="取消" color="neutral" variant="outline" size="md" :disabled="busy" @click="toggleTarget = null" /></div></div></template></UModal>
    <ReferralMaterials :campaign="materialTarget" :actor="user.id" @close="materialTarget = null" />
    <ReferralCampaignDetail :id="detailTarget" :initial-expenses="requestedExpenses && detailTarget === requested" @close="detailTarget = ''; emit('close-detail')" @select="selectDetail" />
  </div></section>
</template>
