<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import '../xhs-workflow.css'
import XhsReviewIdeas from './XhsReviewIdeas.vue'
import XhsDraftRecovery from './XhsDraftRecovery.vue'
import { computed, onActivated, ref, watch } from 'vue'
import { ApiError, type UserInfo } from '../api'
import { adminRoute, navigateAdmin, useAdminLeaveGuard } from '../navigation'
import { useXhsDraftBackup } from '../xhs-draft-backup'
import { dateTimeLocal, getAnalytics, getMetrics, getWorkflow, isoDateTime, saveReview, workflowError, workflowFingerprint, type AnalyticsRecord, type AnalyticsSort, type MetricData, type PublicationData, type ReviewSave, type WorkflowRecord } from '../xhs-workflow'
const props = defineProps<{ user: UserInfo }>()
const checkpoint = ref<1 | 3 | 7>(7), page = ref(1), q = ref(''), account = ref('__all__'), sort = ref<AnalyticsSort>('published_at'), startDate = ref(''), endDate = ref('')
const accounts = ref<{id: string; name: string}[]>([]), items = ref<AnalyticsRecord[]>([]), total = ref(0), error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false)
const record = ref<WorkflowRecord<PublicationData> | null>(null), metrics = ref<MetricData[]>([]), conclusion = ref(''), nextAction = ref('')
const emptyMetric = (value: 1 | 3 | 7): MetricData => ({ checkpoint: value, revision: 0, measured_at: new Date().toISOString(), views: 0, likes: 0, saves: 0, comments: 0, follows: null, downloads: null, notes: '' })
const form = ref(emptyMetric(7)), baseline = ref('')
const pendingSave = ref<(ReviewSave & { id: string }) | null>(null)
const snapshot = () => JSON.stringify([form.value, conclusion.value, nextAction.value])
const dirty = computed(() => !!record.value && snapshot() !== baseline.value)
const backup = useXhsDraftBackup({ adminId: props.user.id, scope: () => `analytics:${record.value?.id || ''}:${checkpoint.value}`,
  enabled: () => !!record.value && !loading.value, dirty: () => dirty.value,
  snapshot: () => ({ form: form.value, conclusion: conclusion.value, nextAction: nextAction.value, pendingSave: pendingSave.value }),
  revision: () => `${record.value?.revision || 0}:${metrics.value.find(item => item.checkpoint === checkpoint.value)?.revision || 0}`,
  restore: value => { form.value = value.form; conclusion.value = value.conclusion; nextAction.value = value.nextAction; pendingSave.value = value.pendingSave || null } })
useAdminLeaveGuard(() => {
  if (adminRoute.tab !== 'xhsAnalytics') return true
  if (busy.value) { error.value = '正在保存复盘，请等待保存完成。'; return false }
  backup.persist(); return !dirty.value || window.confirm('复盘记录尚未保存，是否离开？已成功备份的编辑可在本机恢复。')
})
let sequence = 0
function chooseCheckpoint(value: 1 | 3 | 7) {
  if (record.value) navigateAdmin('xhsAnalytics', { id: record.value.id, checkpoint: String(value) })
  else checkpoint.value = value
}
function dates() {
  const start = startDate.value ? new Date(startDate.value + 'T00:00:00') : null
  const end = endDate.value ? new Date(endDate.value + 'T00:00:00') : null
  if (end) end.setDate(end.getDate() + 1)
  if (start && end && start >= end) throw new Error('开始日期不能晚于结束日期。')
  return { ...(start ? { start: start.toISOString() } : {}), ...(end ? { end: end.toISOString() } : {}) }
}
async function load() {
  if (adminRoute.tab !== 'xhsAnalytics') return
  const seq = ++sequence; loading.value = true; error.value = ''
  try {
    const params = new URLSearchParams(adminRoute.query), id = params.get('id')
    if (id) {
      const [entry, values] = await Promise.all([getWorkflow<PublicationData>('publications', id), getMetrics(id)])
      if (seq !== sequence) return
      record.value = entry; metrics.value = values.items; pendingSave.value = null
      const day = Number(params.get('checkpoint'))
      if (day === 1 || day === 3 || day === 7) checkpoint.value = day
      const saved = metrics.value.find(item => item.checkpoint === checkpoint.value)
      form.value = saved ? { ...saved } : emptyMetric(checkpoint.value)
      conclusion.value = entry.data.conclusion; nextAction.value = entry.data.next_action; baseline.value = snapshot()
    } else {
      record.value = null
      const result = await getAnalytics(checkpoint.value, q.value, page.value, { account: account.value === '__all__' ? '' : account.value, sort: sort.value, ...dates() })
      if (seq !== sequence) return
      items.value = result.items; total.value = result.total; accounts.value = result.accounts || []
    }
  } catch (cause) { if (seq === sequence) error.value = workflowError(cause) }
  finally { if (seq === sequence) loading.value = false }
}
async function save() {
  if (!record.value || busy.value || loading.value || backup.recovery.value) return
  const sourceRoute = adminRoute.query, sourceId = record.value.id, day = checkpoint.value
  const current = () => adminRoute.tab === 'xhsAnalytics' && adminRoute.query === sourceRoute && record.value?.id === sourceId && checkpoint.value === day
  const metricFingerprint = (metric: MetricData) => workflowFingerprint({ ...metric, revision: 0, measured_at: new Date(metric.measured_at).toISOString() })
  function accept(result: { record: WorkflowRecord<PublicationData>; items: MetricData[] }, attempt: ReviewSave, recovered = false) {
    if (!current()) return
    const saved = result.items.find(item => item.checkpoint === day)!
    const unchanged = workflowFingerprint([form.value, conclusion.value, nextAction.value]) === workflowFingerprint([attempt.metric, attempt.conclusion, attempt.next_action])
    backup.clear(); pendingSave.value = null; record.value = result.record; metrics.value = result.items
    baseline.value = JSON.stringify([saved, result.record.data.conclusion, result.record.data.next_action])
    if (unchanged) { form.value = { ...saved }; conclusion.value = result.record.data.conclusion; nextAction.value = result.record.data.next_action }
    else form.value.revision = saved.revision
    error.value = ''
    notice.value = dirty.value ? '原复盘已保存，之后的编辑已保留，请再次保存。' : recovered ? '已查询确认原复盘完整保存成功。' : '数据和复盘已保存'
    if (dirty.value) backup.persist()
  }
  async function recover(attempt: ReviewSave) {
    const [savedRecord, values] = await Promise.all([getWorkflow<PublicationData>('publications', sourceId), getMetrics(sourceId)])
    if (!current()) return true
    const metric = values.items.find(item => item.checkpoint === day)
    if (metric && metric.revision > attempt.metric.revision && metricFingerprint(metric) === metricFingerprint(attempt.metric) &&
      workflowFingerprint([savedRecord.data.conclusion, savedRecord.data.next_action]) === workflowFingerprint([attempt.conclusion, attempt.next_action])) {
      accept({ record: savedRecord, items: values.items }, attempt, true); return true
    }
    if (savedRecord.revision !== attempt.revision || (metric?.revision || 0) !== attempt.metric.revision) {
      throw new ApiError('复盘已在其他页面更新，当前输入已保留，请核对最新版本。', 409)
    }
    return false
  }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (pendingSave.value && await recover(pendingSave.value)) return
    const attempt = pendingSave.value || { id: sourceId, revision: record.value.revision, metric: JSON.parse(JSON.stringify(form.value)) as MetricData, conclusion: conclusion.value, next_action: nextAction.value }
    pendingSave.value = attempt; backup.persist()
    try {
      const { id: _id, ...payload } = attempt
      accept(await saveReview(sourceId, payload), payload)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408) { pendingSave.value = null; throw cause }
      if (!await recover(attempt)) throw cause
    }
  } catch (cause) { if (current()) { error.value = workflowError(cause); backup.persist() } }
  finally { busy.value = false }
}
function open(id?: string) { navigateAdmin('xhsAnalytics', id ? { id, checkpoint: String(checkpoint.value) } : {}) }
function search() { if (page.value !== 1) page.value = 1; else void load() }
function reset() { q.value = ''; account.value = '__all__'; startDate.value = ''; endDate.value = ''; sort.value = 'published_at'; search() }
watch(() => [adminRoute.tab, adminRoute.query], () => { void load() })
onActivated(() => { if (!dirty.value && !loading.value) void load() })
watch([account, sort, checkpoint], () => { if (!record.value) search() }); watch(page, () => { if (!record.value) void load() })
const fields = [{ key:'views',label:'浏览量' },{ key:'likes',label:'点赞数' },{ key:'saves',label:'收藏数' },{ key:'comments',label:'评论数' },{ key:'follows',label:'新增关注（选填）' },{ key:'downloads',label:'资料下载（选填）' }] as const
function metricNumber(key: typeof fields[number]['key'], value: string) { if (value === '' && (key === 'follows' || key === 'downloads')) form.value[key] = null; else form.value[key] = Number(value) }
</script>
<template><section class="admin-section xhs-workflow"><header class="workflow-heading"><div><h2>效果复盘</h2><p>按相同观察阶段比较数据，找出值得继续做的选题；数据由你从小红书后台录入。</p></div><div class="workflow-actions"><template v-if="record"><UButton label="返回对比列表" color="neutral" variant="outline" @click="open()" /><UButton v-permission="'xhsAnalytics:update'" label="保存复盘" :loading="busy" :disabled="loading || !!backup.recovery.value" @click="save" /></template><UButton v-permission="'xhsPublishing:view'" v-else label="去发布管理" variant="outline" @click="navigateAdmin('xhsPublishing')" /></div></header><UAlert v-if="error" :title="error" color="error" role="alert" /><UAlert v-if="notice" :title="notice" color="success" role="status" /><div class="workflow-actions my-4"><UButton v-for="day in ([1,3,7] as const)" :key="day" :label="`发布后第 ${day} 天`" :variant="checkpoint===day?'solid':'outline'" @click="record?chooseCheckpoint(day):checkpoint=day" /></div><p v-if="loading" class="workflow-hint">正在读取…</p><template v-if="!record"><form class="workflow-actions analytics-filters" @submit.prevent="search"><UInput v-model="q" class="analytics-query" aria-label="搜索发布记录" placeholder="搜索发布记录" maxlength="120" /><USelect v-model="account" class="analytics-account" aria-label="复盘账号筛选" :items="[{value:'__all__',label:'全部账号'},...accounts.map(item=>({value:item.id,label:item.name}))]" /><label>发布开始日期<input v-model="startDate" class="workflow-native" type="date" aria-label="复盘开始日期" /></label><label>发布结束日期<input v-model="endDate" class="workflow-native" type="date" aria-label="复盘结束日期" /></label><USelect v-model="sort" class="analytics-sort" aria-label="复盘排序" :items="[{value:'published_at',label:'发布时间：新到旧'},{value:'save_rate',label:'收藏率：高到低'},{value:'interaction_rate',label:'互动率：高到低'},{value:'views',label:'浏览量：高到低'}]" /><div class="analytics-filter-actions"><UButton label="搜索" type="submit" variant="outline" :loading="loading" /><UButton label="清空筛选" variant="ghost" @click="reset" /></div></form><div class="workflow-step">“待录入”表示已经到了观察日期，还未填写数据。收藏率 = 收藏数 ÷ 浏览量；互动率 =（点赞 + 收藏 + 评论）÷ 浏览量。缺失数据用“—”显示。日期按本机时区筛选实际发布时间；排序覆盖全部筛选记录，缺失数据和零浏览的比例排在最后。</div><div class="data-scroll"><table class="data-table"><thead><tr><th>笔记 / 账号</th><th>浏览</th><th>收藏</th><th>收藏率</th><th>互动率</th><th>跟进</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td><strong>{{ item.title }}</strong><p>{{ item.data.account || '未填写账号' }}</p></td><td>{{ item.metric?.views ?? '—' }}</td><td>{{ item.metric?.saves ?? '—' }}</td><td>{{ item.save_rate===null?'—':item.save_rate+'%' }}</td><td>{{ item.interaction_rate===null?'—':item.interaction_rate+'%' }}</td><td><UButton :label="item.metric?'查看 / 修改':item.needs_recording?'待录入':'记录数据'" size="sm" variant="outline" @click="open(item.id)" /><XhsReviewIdeas v-if="item.metric" :publication-id="item.id" :checkpoint="checkpoint" /></td></tr><tr v-if="!items.length"><td colspan="6" class="workflow-empty">当前没有符合条件的已发布记录。可清空筛选，或先登记实际发布。</td></tr></tbody></table></div><UPagination v-if="total>20" v-model:page="page" :total="total" :items-per-page="20" /></template><div v-else class="workflow-editor"><XhsDraftRecovery :backup="backup" /><div class="workflow-editor" :inert="busy || loading || !!backup.recovery.value"><div class="workflow-step"><strong>{{ record.title }}</strong><p>{{ record.data.account }}</p><a :href="record.data.url" target="_blank" rel="noreferrer">打开已发布笔记 ↗</a></div><div class="workflow-card workflow-grid"><label class="workflow-field workflow-wide"><span>实际统计时间</span><input class="workflow-native" type="datetime-local" :value="dateTimeLocal(form.measured_at)" @input="form.measured_at=isoDateTime(($event.target as HTMLInputElement).value) || ''" /></label><label v-for="field in fields" :key="field.key" class="workflow-field"><span>{{ field.label }}</span><input class="workflow-native" type="number" min="0" max="10000000000" step="1" :aria-label="field.label" :value="form[field.key] ?? ''" @input="metricNumber(field.key,($event.target as HTMLInputElement).value)" /></label><label class="workflow-field workflow-wide"><span>本阶段观察</span><UTextarea v-model="form.notes" :rows="3" maxlength="2000" placeholder="读者主要问了什么？哪些页面或题目反馈较多？" /></label></div><div class="workflow-card workflow-grid"><label class="workflow-field workflow-wide"><span>这篇内容的结论</span><UTextarea v-model="conclusion" aria-label="复盘结论" :rows="4" maxlength="4000" placeholder="哪些做法有效？哪些还需要验证？" /></label><label class="workflow-field workflow-wide"><span>下一步行动</span><UTextarea v-model="nextAction" :rows="3" maxlength="2000" placeholder="例如：再做一份进阶版本，对比收藏率" /></label><XhsReviewIdeas :publication-id="record.id" :checkpoint="checkpoint" :disabled="busy || snapshot()!==baseline || !metrics.some(item=>item.checkpoint===checkpoint)" /><p class="workflow-hint">保存当前阶段的数据与结论后，可整理后续选题。</p></div></div></div></section></template>

<style scoped>
.analytics-filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px;align-items:end}
.analytics-filters label{display:grid;gap:4px;font-size:12px;order:3}
.analytics-filters :deep(.analytics-query){order:0;width:100%}
.analytics-filters :deep(.analytics-account){order:1;width:100%}
.analytics-filters :deep(.analytics-sort){order:2;width:100%}
.analytics-filter-actions{display:flex;gap:8px;order:4;align-self:end}
@media(max-width:900px){.analytics-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.analytics-filters{grid-template-columns:1fr}}
</style>
