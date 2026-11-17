<script setup lang="ts">
import { ref, watch } from 'vue'
import { permissionDirective as vPermission } from '../permissions'
import { useAdminPage } from '../admin-page'
import { catalogList, catalogDetail, type CatalogDetail, type CatalogPaper } from '../catalog'
import { cancelSchedule, getCatalogHealth, getSchedule, getSchedules, localDateTime, probeCatalogLink, saveSchedule } from '../catalog-operations'
import type { HealthItem, ScheduleItem } from '../../../shared/teaching'
const props = defineProps<{ mode: 'schedules' | 'health' }>()
const emit = defineEmits<{ close: []; saved: []; edit: [id: string] }>()
const schedules = ref<ScheduleItem[]>([]), health = ref<HealthItem[]>([]), total = ref(0), offset = ref(0), more = ref(false)
const q = ref(''), onlyIssues = ref(false), choices = ref<CatalogPaper[]>([]), searchText = ref(''), choiceMore = ref(false), choiceOffset = ref(0)
const scheduleStatus = ref(''), healthCategory = ref(''), counts = ref<Record<string, number>>({})
const categories = [{ value: 'file', label: '文件异常' }, { value: 'preview', label: '预览问题' }, { value: 'textbook', label: '教材标签' }, { value: 'review', label: '内容待核对' }, { value: 'answers', label: '答案待处理' }, { value: 'link', label: '网盘待核验' }]
const statuses = [{ value: '', label: '全部' }, { value: 'pending', label: '待发布' }, { value: 'failed', label: '失败待处理' }, { value: 'published', label: '已发布' }, { value: 'cancelled', label: '已取消' }]
const target = ref<CatalogDetail | null>(null), existing = ref<ScheduleItem | null>(null), time = ref(''), confirmed = ref(false)
const choosing = ref(false)
const labels = { pending: '待发布', published: '已发布', failed: '失败待处理', cancelled: '已取消' }
const answerLabels: Record<string, string> = { included: '文件内含答案', separate: '有配套答案', missing: '未提供答案', unknown: '待核对' }
const page = useAdminPage(async valid => {
  const result = props.mode === 'schedules' ? await getSchedules(offset.value, scheduleStatus.value) : await getCatalogHealth(q.value, offset.value, onlyIssues.value, healthCategory.value)
  if (!valid()) return
  total.value = result.total; more.value = result.has_more; counts.value = result.counts || {}
  const lastOffset = Math.max(0, Math.ceil(result.total / 20) - 1) * 20
  if (offset.value > lastOffset) { offset.value = lastOffset; void page.load(); return }
  if (props.mode === 'schedules') schedules.value = (result as Awaited<ReturnType<typeof getSchedules>>).items
  else health.value = (result as Awaited<ReturnType<typeof getCatalogHealth>>).items
})
const { loading, busy, error, notice } = page
function search() { offset.value = 0; void page.load() }
function changePage(delta: number) { offset.value += delta * 20; void page.load() }
function resetTarget() { target.value = null; existing.value = null; confirmed.value = false; time.value = '' }
async function findChoices(reset = true) {
  choosing.value = true
  await page.act(async valid => {
    const nextOffset = reset ? 0 : choiceOffset.value + 20
    const result = await catalogList(searchText.value, 'draft', nextOffset)
    if (valid()) { choices.value = reset ? result.items : [...choices.value, ...result.items]; choiceOffset.value = nextOffset; choiceMore.value = result.has_more }
  })
}
async function choose(id: string) {
  await page.act(async valid => {
    const detail = await catalogDetail(id)
    const schedule = await getSchedule(id)
    if (valid()) { target.value = detail; existing.value = schedule; confirmed.value = false; time.value = localDateTime(schedule?.status === 'pending' ? schedule.scheduled_at : Math.floor(Date.now() / 1000) + 3600) }
  })
}
async function save() {
  const item = target.value
  if (!item || !confirmed.value) return
  const epoch = Math.floor(new Date(time.value).getTime() / 1000)
  if (!Number.isFinite(epoch) || epoch < Date.now() / 1000 + 60) { error.value = '请选择至少 1 分钟后的发布时间'; return }
  await page.act(async valid => {
    await saveSchedule(item.id, item.revision, existing.value?.revision || 0, epoch)
    if (valid()) { resetTarget(); notice.value = '已保存排期；资料版本变化后会暂停发布，等待重新核对'; emit('saved'); await page.load() }
  })
}
async function cancel(item: ScheduleItem) {
  if (!window.confirm('取消“' + item.title + '”的定时发布？')) return
  await page.act(async valid => { await cancelSchedule(item); if (valid()) { notice.value = '已取消'; await page.load(); emit('saved') } })
}
async function probe(item: HealthItem, manual = false) {
  if (manual && !window.confirm('确认你已打开网盘，核对分享文件和提取码可以正常使用？')) return
  await page.act(async valid => { const result = await probeCatalogLink(item.catalog_id, manual); if (valid()) { notice.value = result.message; await page.load() } })
}
function edit(id: string) { emit('edit', id); emit('close') }
watch([onlyIssues, healthCategory, scheduleStatus], search)
watch(() => props.mode, () => { offset.value = 0; counts.value = {}; resetTarget(); void page.load() })
</script>
<template>
  <UModal :open="true" :title="mode === 'schedules' ? '资料发布排期' : '资料体检'" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-4xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <p class="text-sm text-muted mb-4">{{ mode === 'schedules' ? '时间按当前设备时区显示。到时重新检查内容版本、发布权限和文件；停机后会在服务恢复时补发。' : '检查管理范围内的全部资料，按问题类型筛选后分页显示。自动检测只提示网盘链接的疑似异常，需人工核对文件与提取码。' }}</p>
      <UAlert v-if="error" :title="error" color="error" class="mb-3" /><UAlert v-if="notice" :title="notice" color="success" class="mb-3" />
      <div class="flex gap-3 items-center flex-wrap mb-4"><UButton label="刷新" variant="outline" :loading="loading" :disabled="busy" @click="page.load" /><template v-if="mode === 'health'"><form class="ops-search" @submit.prevent="search"><UInput v-model="q" :maxlength="120" placeholder="搜索资料标题" aria-label="体检资料搜索" /><UButton label="搜索" type="submit" :disabled="busy" /></form><UCheckbox v-model="onlyIssues" label="仅显示异常资料（全部页面）" :disabled="busy" /></template><UButton v-else v-permission="'papers:publish'" label="选择草稿并安排发布" icon="i-lucide-calendar-plus" :disabled="busy" @click="findChoices()" /></div>
      <div v-if="mode === 'schedules'" class="ops-filter-tabs" aria-label="排期状态筛选"><UButton v-for="item in statuses" :key="item.value" :label="item.label + '（' + (counts[item.value || 'all'] || 0) + '）'" :variant="scheduleStatus === item.value ? 'solid' : 'outline'" :color="item.value === 'failed' && counts.failed ? 'error' : 'primary'" :aria-pressed="scheduleStatus === item.value" :disabled="busy" @click="scheduleStatus = item.value" /></div>
      <template v-else><p class="text-sm text-muted mb-3" role="status">{{ q.trim() ? '当前标题搜索范围' : '管理范围内全部资料' }}：{{ counts.all || 0 }} 份 · {{ counts.issues || 0 }} 份有提示；同一份资料可能有多类问题。</p><div class="ops-filter-tabs" aria-label="体检问题分类"><UButton label="全部类型" :variant="!healthCategory ? 'solid' : 'outline'" :aria-pressed="!healthCategory" :disabled="busy" @click="healthCategory = ''" /><UButton v-for="item in categories" :key="item.value" :label="item.label + '（' + (counts[item.value] || 0) + '）'" :variant="healthCategory === item.value ? 'solid' : 'outline'" :aria-pressed="healthCategory === item.value" :disabled="busy" @click="healthCategory = item.value" /></div></template>
      <section v-if="mode === 'schedules' && choosing" class="ops-choice"><form class="flex gap-2" @submit.prevent="findChoices()"><UInput v-model="searchText" placeholder="搜索待发布草稿" aria-label="排期草稿搜索" /><UButton type="submit" label="搜索草稿" :disabled="busy" /></form><div v-for="item in choices" :key="item.id" class="ops-row"><span>{{ item.title }} · {{ item.grade }} {{ item.subject }}</span><UButton label="选择" size="xs" :disabled="busy" @click="choose(item.id)" /></div><UButton v-if="choiceMore" label="更多草稿" variant="ghost" :disabled="busy" @click="findChoices(false)" /></section>
      <p v-if="mode === 'schedules' && !choices.length && !target" class="text-sm text-muted">可选择已准备好的草稿；已发布的资料无需排期。</p>
      <section v-if="target" class="ops-form">
        <strong>{{ target.title }}</strong><p>{{ target.grade }} · {{ target.subject }} · 当前资料版本 {{ target.revision }}</p>
        <p>观看权限：{{ target.required_view === 'vip' ? '会员' : '普通用户' }}；下载权限：{{ target.required_download === 'vip' ? '会员' : '普通用户' }}；答案状态：{{ answerLabels[target.answer_readiness || "unknown"] || "待核对" }}</p>
        <UButton label="打开资料预览并核对" variant="outline" :disabled="busy" @click="edit(target.id)" />
        <label class="ops-date">发布时间<input v-model="time" type="datetime-local" aria-label="资料发布时间" :disabled="busy" /></label>
        <UCheckbox v-model="confirmed" label="我已核对当前资料、答案、文件及会员权限，确认到时公开发布" :disabled="busy" />
        <div class="flex gap-2"><UButton v-permission="'papers:publish'" label="保存排期" :loading="busy" :disabled="!confirmed" @click="save" /><UButton label="取消选择" variant="ghost" :disabled="busy" @click="resetTarget" /></div>
      </section>
      <div v-if="mode === 'schedules'">
        <article v-for="item in schedules" :key="item.catalog_id" class="ops-card"><div class="ops-row"><strong>{{ item.title }}</strong><UBadge :color="item.status === 'failed' ? 'error' : item.status === 'published' ? 'success' : 'neutral'">{{ labels[item.status] }}</UBadge></div><p>{{ new Date(item.scheduled_at * 1000).toLocaleString('zh-CN') }} · 资料版本 {{ item.catalog_revision }}</p><p v-if="item.message">{{ item.message }}</p><div class="flex gap-2"><UButton label="查看并修复资料" variant="ghost" size="xs" :disabled="busy" @click="edit(item.catalog_id)" /><UButton v-if="item.status !== 'published'" v-permission="'papers:publish'" label="重新排期" variant="outline" size="xs" :disabled="busy" @click="choose(item.catalog_id)" /><UButton v-if="item.status === 'pending'" v-permission="'papers:publish'" label="取消排期" color="error" variant="ghost" size="xs" :disabled="busy" @click="cancel(item)" /></div></article>
      </div>
      <div v-else><article v-for="item in health" :key="item.catalog_id" class="ops-card"><div class="ops-row"><strong>{{ item.title }}</strong><UBadge :color="item.issues.some(i => i.severity === 'error') ? 'error' : item.issues.length ? 'warning' : 'success'">{{ item.issues.length ? item.issues.length + ' 项提示' : '本次检查正常' }}</UBadge></div><ul><li v-for="issue in item.issues" :key="issue.code">{{ issue.message }}</li></ul><p v-if="item.link_check">最近链接核验：{{ new Date(item.link_check.checked_at * 1000).toLocaleString('zh-CN') }} · {{ item.link_check.message }}</p><div class="flex gap-2 flex-wrap"><UButton label="查看并修复资料" size="xs" variant="outline" :disabled="busy" @click="edit(item.catalog_id)" /><UButton v-if="item.external" label="检测网盘链接" size="xs" variant="ghost" :disabled="busy" @click="probe(item)" /><UButton v-if="item.external" v-permission="'papers:update'" label="人工确认链接可用" size="xs" variant="ghost" :disabled="busy" @click="probe(item, true)" /></div></article></div>
      <p v-if="!loading && !(mode === 'schedules' ? schedules.length : health.length)" class="empty-state">{{ mode === 'health' ? '没有符合条件的资料，可调整搜索或问题分类' : scheduleStatus ? '此状态暂无排期' : '暂无发布排期' }}</p>
      <div class="ops-row mt-4"><UButton label="上一页" variant="outline" :disabled="!offset || loading || busy" @click="changePage(-1)" /><span>第 {{ offset / 20 + 1 }} 页 · 共 {{ total }} 条</span><UButton label="下一页" variant="outline" :disabled="!more || loading || busy" @click="changePage(1)" /></div>
    </template><template #footer><UButton label="完成" :disabled="busy" @click="emit('close')" /></template>
  </UModal>
</template>
<style scoped>
.ops-filter-tabs { display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px; }.ops-search { display:flex;gap:8px;max-width:100%; }.ops-search > :first-child { min-width:0; }.ops-card strong { overflow-wrap:anywhere; }.ops-row { display:flex;align-items:center;justify-content:space-between;gap:12px; }.ops-card { border-top:1px solid var(--ui-border);padding:16px 0;display:grid;gap:10px;font-size:13px; }.ops-card ul { padding-left:20px;line-height:1.8; }.ops-form,.ops-choice { background:var(--ui-bg-elevated);border-radius:10px;padding:16px;margin:16px 0;display:grid;gap:12px;font-size:13px; }.ops-date { display:grid;gap:8px; }.ops-date input { padding:10px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-bg); }@media(max-width:600px) { .ops-row { flex-wrap:wrap; } }
</style>
