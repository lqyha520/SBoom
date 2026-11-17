<script setup lang="ts">
import { permissionDirective as vPermission, canAdmin, canPermission } from '../permissions'
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { navigateAdmin } from '../navigation'
import XhsNoteLibrary from './XhsNoteLibrary.vue'
import { listXhsAccounts, openXhsNote, type XhsAccount } from '../xhs-accounts'
import type { LibraryNote } from '../xhs-research'
import { bindResearchAccounts, researchBindings, savedResearchSelection, selectionKey } from '../xhs-research-accounts'
import { executeResearchQueue, executeResearchTask } from '../xhs-queue'
import {
  CollectorError, createResearchBatch, createResearchTask, deleteResearchTask, getCollectorStatus,
  getCollectionAccount, getResearchBatch, getResearchTask, listResearchBatches, listResearchTasks, openCollectorBrowser, progressLabels, researchSearchUrl,
  setCollectorEnabled, type BatchSummary, type CollectionProgress, type ResearchBatch, type ResearchPeriod, type ResearchSort, type ResearchTask,
} from '../xhs-research'

const props = defineProps<{ user: UserInfo }>()
const grades = ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '七年级', '八年级', '九年级', '高一', '高二', '高三']
const subjects = ['语文', '数学', '英语', '物理', '化学', '生物', '历史', '地理', '政治']
const periodOptions: { label: string; value: ResearchPeriod }[] = [
  { label: '一天内', value: 'day' }, { label: '一周内', value: 'week' },
  { label: '半年内', value: 'half_year' }, { label: '不限时间', value: 'all' },
]
const sortOptions: { label: string; value: ResearchSort }[] = [
  { label: '最多点赞', value: 'popular' }, { label: '综合排序', value: 'general' }, { label: '最新发布', value: 'latest' },
]
const limitOptions = [10, 20, 30, 50, 100].map(value => ({ label: `${value} 条`, value }))
const form = ref({ grade: '一年级', subject: '数学', keyword: '', period: 'week' as ResearchPeriod,
  sort_by: 'popular' as ResearchSort, note_limit: 10 })
const tasks = ref<ResearchTask[]>([])
const taskPage = ref(1)
const taskPageSize = 10
const taskTotal = ref(0)
const selectedTask = ref<ResearchTask | null>(null)
const libraryRefresh = ref(0)
const batchMode = ref(false), batchKeywords = ref(''), batch = ref<ResearchBatch | null>(null), batches = ref<BatchSummary[]>([])
const progress = ref<CollectionProgress | null>(null), pauseRequested = ref(false), queueRunning = ref(false), errorCode = ref('')
const loading = ref(false)
const selectingTask = ref(false)
const showAdvanced = ref(false)
const submitting = ref(false)
const deletingId = ref('')
const error = ref('')
const notice = ref('')
const collectorConnected = ref(false)
const collectorEnabled = ref(false)
const collectorPauseReason = ref('')
const collectorBusy = ref(false)
const collectorVersion = ref(0), accounts = ref<XhsAccount[]>([]), accountsLoading = ref(false), accountError = ref('')
const selectedAccount = ref(savedResearchSelection()), actionAccount = ref('')
const openingNoteId = ref('')
const accountOptions = computed(() => accounts.value.filter(item => !item.archived).map(item => ({
  value: item.id, label: `${item.name}${item.busy ? ' · 正在使用' : ''}`,
})))
const selectedAccountInfo = computed(() => accounts.value.find(item => item.id === selectedAccount.value && !item.archived))
const bridgeReady = computed(() => collectorConnected.value && collectorEnabled.value && collectorVersion.value >= 10)
const accountName = (id: string) => accounts.value.find(item => item.id === id)?.name || '原账号（请在账号管理中检查）'
watch(selectedAccount, value => { try { localStorage.setItem(selectionKey, value) } catch { /* 选择记忆失败不影响已持久化的任务绑定。 */ } })
let requestId = 0
let active = true
let collectorTimer: ReturnType<typeof setTimeout> | undefined
let collectorRefresh: Promise<void> | undefined, selectionRequest = 0

const periodLabels: Record<ResearchPeriod, string> = { day: '一天内', week: '一周内', half_year: '半年内', all: '不限时间' }
const statusLabels: Record<string, string> = { queued: '待启动', running: '采集中', completed: '已完成', failed: '失败' }
const canCollect = computed(() => bridgeReady.value && !!selectedAccountInfo.value && !selectedAccountInfo.value.busy && !collectorBusy.value)
const collectorLabel = computed(() => !collectorConnected.value ? '采集器未连接' : collectorEnabled.value ? '采集器已开启' : '采集器已关闭')
const collectionHint = computed(() => !collectorConnected.value ? '连接本机采集器后即可开始采集' : collectorVersion.value < 10 ? '请更新并重启本机采集器' : collectorPauseReason.value ? '采集已暂停，请先人工检查并确认可继续' : !collectorEnabled.value ? '开启采集器后即可开始' : !selectedAccountInfo.value ? '请选择一个采集账号' : selectedAccountInfo.value.busy || collectorBusy.value ? '采集环境正在使用，请稍后再试' : '已准备好，采集将在所选账号的浏览器中进行')
const queueRemaining = computed(() => batch.value?.items.filter(task => task.status !== 'completed').length || 0)
function message(cause: unknown) { return cause instanceof Error ? cause.message : '操作失败，请重试' }
function taskAccountName(task: ResearchTask) {
  try { const id = researchBindings()[task.id]; return id ? accountName(id) : '尚未绑定账号' }
  catch { return '账号记录读取失败' }
}
function compactDate(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '—' }
function sortLabel(value: ResearchSort) { return sortOptions.find(option => option.value === value)?.label || value }
function resultLabel() { return progress.value?.cached ? '已取回最近采集的快照' : '采集完成' }

async function refreshCollector() {
  if (collectorRefresh) return collectorRefresh
  collectorRefresh = (async () => {
    const status = await getCollectorStatus()
    if (!active) return
    collectorConnected.value = status.connected
    collectorEnabled.value = status.enabled
    collectorPauseReason.value = status.pause_reason || ''
    collectorBusy.value = status.busy
    collectorVersion.value = status.version || 0
    if (status.connected && collectorVersion.value >= 5) await refreshAccounts()
  })()
  try { await collectorRefresh } finally { collectorRefresh = undefined }
}

async function refresh() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const [result] = await Promise.all([listResearchTasks(taskPage.value, taskPageSize), refreshCollector()])
    if (id !== requestId || !active) return
    const lastPage = Math.max(1, Math.ceil(result.total / taskPageSize))
    if (taskPage.value > lastPage) {
      taskPage.value = lastPage
      return
    }
    tasks.value = result.items
    taskTotal.value = result.total
    if (selectedTask.value) {
      const latest = result.items.find(task => task.id === selectedTask.value?.id)
      if (latest) selectedTask.value = latest
    }
  } catch (cause) { if (id === requestId) error.value = message(cause) }
  finally { if (id === requestId) loading.value = false }
}

async function refreshAccounts() {
  if (!canAdmin('xhsAccounts')) return
  if (accountsLoading.value) return
  accountsLoading.value = true
  try {
    accounts.value = (await listXhsAccounts()).items
    accountError.value = ''
    if (selectedAccount.value && !accounts.value.some(item => item.id === selectedAccount.value && !item.archived)) selectedAccount.value = ''
  } catch (cause) { accounts.value = []; accountError.value = message(cause) }
  finally { accountsLoading.value = false }
}

async function openBrowser(accountId = selectedAccount.value) {
  error.value = ''
  try {
    if (!accountId) throw new Error('请先选择采集账号。')
    await openCollectorBrowser(accountId)
    await refreshCollector()
    notice.value = `已打开「${accountName(accountId)}」的浏览器。请检查原页面、登录或验证状态，确认可以继续后再恢复采集。`
  } catch (cause) { error.value = message(cause) }
}

async function viewNote(note: LibraryNote) {
  if (openingNoteId.value) return
  error.value = ''; notice.value = ''
  const account = selectedAccountInfo.value
  try {
    if (!account) throw new Error('请先在采集条件中选择查看笔记使用的账号。')
    if (!collectorConnected.value) throw new Error('本机采集器未连接，请连接后再查看笔记。')
    if (collectorVersion.value < 8) throw new Error('请重启更新后的本机采集器，才能用所选账号打开笔记。')
    if (account.busy) throw new Error(`「${account.name}」正在使用，请稍后再查看笔记。`)
    openingNoteId.value = note.note_id
    await openXhsNote(account.id, note.url)
    notice.value = `已在「${account.name}」的浏览器打开笔记。`
  } catch (cause) { error.value = message(cause) }
  finally { openingNoteId.value = '' }
}

function requireBridge() {
  if (!collectorConnected.value) throw new Error('本机采集器未连接，请检查本机启动状态后刷新。')
  if (collectorVersion.value < 10) throw new Error('本机采集器版本较旧，请重启更新后的采集器。')
  if (!collectorEnabled.value) throw new Error('采集器已关闭，请先开启采集器。')
}

async function resolveAccounts(items: ResearchTask[]): Promise<Record<string, string> | null> {
  const bindings = researchBindings(), resolved: Record<string, string> = {}, missing: ResearchTask[] = []
  for (const task of items.filter(item => item.status !== 'completed')) {
    const cached = await getCollectionAccount(task.id)
    if (cached && bindings[task.id] && cached !== bindings[task.id]) throw new Error('本机缓存和任务账号记录不一致，已停止采集。请检查原账号。')
    const id = cached || bindings[task.id]
    if (id) resolved[task.id] = id
    else missing.push(task)
  }
  if (missing.length) {
    if (!selectedAccountInfo.value) throw new Error('这些历史任务尚未绑定账号，请先选择采集账号。')
    if (!window.confirm(`有 ${missing.length} 项任务在本机没有账号记录。确定使用「${selectedAccountInfo.value.name}」采集并绑定这些任务吗？已绑定的任务仍使用原账号。`)) return null
    for (const task of missing) resolved[task.id] = selectedAccount.value
  }
  for (const [taskId, id] of Object.entries(resolved)) {
    const account = accounts.value.find(item => item.id === id && !item.archived)
    if (!account) throw new Error('任务的原账号已归档或不在本机。请恢复原账号；需要换号时请创建新任务。')
    if (account.busy) throw new Error(`「${account.name}」正在使用，请稍后再试。`)
    bindResearchAccounts([{ id: taskId }], id)
  }
  return resolved
}

async function toggleCollector() {
  if (!collectorConnected.value || collectorBusy.value || submitting.value) return
  error.value = ''
  notice.value = ''
  try {
    const confirmed = !collectorEnabled.value && !!collectorPauseReason.value
    if (confirmed && !window.confirm('采集曾因访问异常或原因不明的结果暂停，这不代表已确认账号被风控。请先人工检查官方 App、原页面和网络。现在确认可继续采集吗？')) return
    const status = confirmed ? await setCollectorEnabled(true, true) : await setCollectorEnabled(!collectorEnabled.value)
    collectorConnected.value = status.connected
    collectorEnabled.value = status.enabled
    collectorPauseReason.value = status.pause_reason || ''
    collectorBusy.value = status.busy
    notice.value = status.enabled ? '采集器已开启，可以开始采集。' : '采集器已关闭。'
  } catch (cause) { error.value = message(cause) }
}

async function runTask(task: ResearchTask) {
  if (submitting.value) return
  submitting.value = true
  error.value = ''
  notice.value = ''
  errorCode.value = ''; progress.value = null
  try {
    requireBridge()
    const resolved = await resolveAccounts([task])
    if (!resolved) return
    actionAccount.value = resolved[task.id] || ''
    selectedTask.value = { ...task, status: 'running' }
    const completed = await executeResearchTask(props.user.id, task, actionAccount.value, value => { progress.value = value })
    selectedTask.value = completed
    libraryRefresh.value++
    notice.value = `${resultLabel()}：保存了 ${completed.note_count} 条公开笔记快照。`
    await refresh()
  } catch (cause) {
    await refresh()
    error.value = message(cause)
    errorCode.value = cause instanceof CollectorError ? cause.code : ''
  } finally { submitting.value = false; progress.value = null }
}

async function createAndRun() {
  if (submitting.value || !form.value.grade || !form.value.subject) return
  submitting.value = true
  error.value = ''
  notice.value = ''
  errorCode.value = ''; progress.value = null
  try {
    requireBridge()
    if (!canCollect.value) throw new Error('请选择可用的采集账号，或等待当前任务完成。')
    const accountId = selectedAccount.value
    actionAccount.value = accountId
    if (batchMode.value) {
      const keywords = [...new Set(batchKeywords.value.split('\n').map(word => word.trim()).filter(Boolean))]
      if (!keywords.length || keywords.length > 20 || keywords.some(word => word.length > 80)) throw new Error('请输入 1–20 行关键词，每行最多 80 字。')
      batch.value = await createResearchBatch(props.user.id, { ...form.value, keyword: '' }, keywords)
      bindResearchAccounts(batch.value.items, accountId)
      await refreshBatches()
      submitting.value = false
      await runQueue()
      return
    }
    const created = await createResearchTask(props.user.id, { ...form.value, keyword: form.value.keyword.trim() })
    bindResearchAccounts([created], accountId)
    if (taskPage.value !== 1) taskPage.value = 1
    else {
      tasks.value = [created, ...tasks.value].slice(0, taskPageSize)
      taskTotal.value++
    }
    selectedTask.value = { ...created, status: 'running' }
    const completed = await executeResearchTask(props.user.id, created, accountId, value => { progress.value = value })
    selectedTask.value = completed
    libraryRefresh.value++
    notice.value = `${resultLabel()}：${completed.grade}${completed.subject}，共保存 ${completed.note_count} 条公开笔记。`
    if (taskPage.value === 1) await refresh()
  } catch (cause) {
    await refresh()
    error.value = message(cause)
    errorCode.value = cause instanceof CollectorError ? cause.code : ''
  } finally { submitting.value = false; progress.value = null }
}

async function refreshBatches() {
  try {
    batches.value = (await listResearchBatches()).items
    if (!batch.value && batches.value.length) batch.value = await getResearchBatch(batches.value[0]!.id)
  } catch (cause) { error.value = message(cause) }
}
async function chooseBatch(id: string) {
  if (submitting.value) return
  try { batch.value = await getResearchBatch(id) }
  catch (cause) { error.value = message(cause) }
}
async function runQueue() {
  if (!batch.value || submitting.value || !bridgeReady.value) return
  submitting.value = true; queueRunning.value = true; pauseRequested.value = false; error.value = ''; notice.value = ''; errorCode.value = ''
  try {
    batch.value = await getResearchBatch(batch.value.id)
    const resolved = await resolveAccounts(batch.value.items)
    if (!resolved) return
    await executeResearchQueue(props.user.id, batch.value.items, {
      accounts: resolved,
      paused: () => pauseRequested.value,
      progress: value => { progress.value = value },
      started: task => { actionAccount.value = resolved[task.id] || ''; selectedTask.value = { ...task, status: 'running' }; task.status = 'running' },
      completed: task => {
        selectedTask.value = task
        const index = batch.value!.items.findIndex(item => item.id === task.id)
        if (index >= 0) batch.value!.items[index] = task
        libraryRefresh.value++
      },
    })
    notice.value = queueRemaining.value ? '本项已保存，队列已暂停。检查结果后，可手动采集下一项。' : '队列采集完成。'
    await refresh()
  } catch (cause) {
    pauseRequested.value = true
    await refresh()
    error.value = `${message(cause)} 队列已暂停，请先处理失败原因。`
    errorCode.value = cause instanceof CollectorError ? cause.code : ''
  } finally {
    submitting.value = false; queueRunning.value = false; progress.value = null
    if (batch.value) {
      try { batch.value = await getResearchBatch(batch.value.id) }
      catch { /* 保留当前队列，稍后手动重新读取。 */ }
    }
    await refreshBatches()
  }
}

async function selectTask(task: ResearchTask) {
  const id = ++selectionRequest
  selectingTask.value = true; error.value = ''
  try { const result = await getResearchTask(task.id); if (id === selectionRequest && active) selectedTask.value = result }
  catch (cause) { if (id === selectionRequest && active) error.value = message(cause) }
  finally { if (id === selectionRequest) selectingTask.value = false }
}

async function removeTask(task: ResearchTask) {
  if (deletingId.value) return
  deletingId.value = task.id
  error.value = ''
  try {
    await deleteResearchTask(props.user.id, task.id)
    tasks.value = tasks.value.filter(item => item.id !== task.id)
    taskTotal.value = Math.max(0, taskTotal.value - 1)
    if (selectedTask.value?.id === task.id) selectedTask.value = null
    if (!tasks.value.length && taskPage.value > 1) taskPage.value--
    else await refresh()
    notice.value = '采集任务已删除，收藏和笔记记录仍保留在笔记库。'
  } catch (cause) { error.value = message(cause) }
  finally { deletingId.value = '' }
}

watch(taskPage, () => { if (active) void refresh() })

function scheduleCollector() {
  if (collectorTimer) clearTimeout(collectorTimer)
  if (!active || document.hidden) return
  collectorTimer = setTimeout(async () => {
    try { await refreshCollector() } finally { scheduleCollector() }
  }, collectorBusy.value ? 5000 : 15000)
}
function visibilityChanged() {
  if (collectorTimer) clearTimeout(collectorTimer)
  if (active && !document.hidden) void refreshCollector().finally(scheduleCollector)
}

onActivated(() => {
  active = true
  void refresh().finally(scheduleCollector)
  void refreshBatches()
  document.addEventListener('visibilitychange', visibilityChanged)
})
onDeactivated(() => {
  active = false
  requestId++
  selectionRequest++; selectingTask.value = false
  if (collectorTimer) clearTimeout(collectorTimer)
  collectorTimer = undefined
  document.removeEventListener('visibilitychange', visibilityChanged)
})
onUnmounted(() => {
  pauseRequested.value = true
  active = false; requestId++; selectionRequest++
  if (collectorTimer) clearTimeout(collectorTimer)
  document.removeEventListener('visibilitychange', visibilityChanged)
})
</script>

<template>
  <section class="admin-section xhs-page" aria-label="小红书选题调研">
    <header class="xhs-hero">
      <div class="hero-copy"><h2>选题调研</h2><p>发现读者问题，收藏参考内容，再转为自己的选题。</p></div>
      <div class="hero-controls">
        <div class="collector-state" :class="!collectorConnected ? 'collector-offline' : collectorEnabled ? 'collector-online' : 'collector-paused'">
        <span class="collector-dot"></span>
          <span>{{ collectorLabel }}</span>
          <UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" size="xs" aria-label="刷新采集器连接" :loading="loading" @click="refresh" />
        </div>
        <UButton v-permission="'xhsResearch:run'" v-if="collectorConnected" :label="collectorEnabled ? '关闭采集器' : '开启采集器'" :icon="collectorEnabled ? 'i-lucide-power-off' : 'i-lucide-power'" color="neutral" :variant="collectorEnabled ? 'outline' : 'solid'" size="sm" :disabled="collectorBusy || submitting" @click="toggleCollector" />
        <UButton v-permission="'xhsResearch:run'" v-if="collectorConnected" label="登录小红书" icon="i-lucide-log-in" color="neutral" variant="ghost" size="sm" :disabled="submitting || !selectedAccountInfo || collectorVersion < 5 || collectorBusy" @click="openBrowser()" />
        <UButton v-if="!collectorConnected" label="刷新连接" icon="i-lucide-refresh-cw" color="neutral" variant="outline" size="sm" :loading="loading" @click="refresh" />
      </div>
    </header>

    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <UAlert v-if="collectorPauseReason" :title="collectorPauseReason" description="暂停原因不一定是账号风控。请先人工检查官方 App、原页面和网络；重启不会自动恢复采集。" color="warning" variant="soft" class="notice" />
    <UButton v-permission="'xhsResearch:run'" v-if="['login', 'verification', 'restricted', 'account_restricted', 'collection_uncertain'].includes(errorCode)" label="打开原页面检查" icon="i-lucide-log-in" size="sm" variant="outline" class="mb-3" @click="openBrowser(actionAccount)" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" class="notice" role="status" />

    <details v-if="!collectorConnected" class="collector-guide">
      <summary>本机采集器未连接 · 查看设置帮助</summary>
      <div class="guide-copy"><span>确认本机采集器已启动后刷新连接。若尚未安装自动启动，请在项目目录运行一次：</span><code>cd admin; pnpm xhs:collector:setup</code></div>
    </details>

    <UAlert v-if="collectorConnected && collectorVersion < 10" title="本机采集器需要更新并重启，以启用数据请求检查和原因不明时暂停。" color="warning" variant="soft" class="notice" />
    <form class="research-form panel-card" @submit.prevent="canPermission('xhsResearch:create') && canAdmin('xhsResearch', 'run') && (createAndRun())">
      <div class="panel-heading form-heading">
        <h3>采集条件</h3>
        <UButton :label="showAdvanced ? '收起筛选' : '更多筛选'" :icon="showAdvanced ? 'i-lucide-chevron-up' : 'i-lucide-sliders-horizontal'" color="neutral" variant="ghost" size="xs" :aria-expanded="showAdvanced" aria-controls="xhs-advanced-fields" @click="showAdvanced = !showAdvanced" />
      </div>
      <div class="research-fields primary-fields">
        <div class="research-field account-select">
          <div class="account-field-label"><span>采集账号</span><div><UButton icon="i-lucide-refresh-cw" aria-label="刷新账号" title="刷新账号" type="button" color="neutral" variant="ghost" size="xs" :loading="accountsLoading" :disabled="submitting || !collectorConnected || collectorVersion < 5" @click="refreshAccounts" /><UButton v-permission="'xhsAccounts:view'" icon="i-lucide-contact-round" aria-label="管理账号" title="管理账号" color="neutral" variant="ghost" size="xs" @click="navigateAdmin('xhsAccounts')" /></div></div>
          <USelect v-model="selectedAccount" :items="accountOptions" placeholder="请选择账号" aria-label="采集账号" :disabled="!canPermission('xhsResearch:create') || (submitting || !!openingNoteId || !collectorConnected || collectorVersion < 5 || accountsLoading)" />
        </div>
        <label class="research-field"><span>年级</span><USelect :disabled="!canPermission('xhsResearch:create')" v-model="form.grade" :items="grades.map(value => ({ label: value, value }))" aria-label="年级" /></label>
        <label class="research-field"><span>科目</span><USelect :disabled="!canPermission('xhsResearch:create')" v-model="form.subject" :items="subjects.map(value => ({ label: value, value }))" aria-label="科目" /></label>
        <label v-if="!batchMode" class="research-field research-keyword"><span>知识点 <small>选填</small></span><UInput :disabled="!canPermission('xhsResearch:create')" v-model="form.keyword" maxlength="80" placeholder="例如：找规律、分数应用题" aria-label="知识点或补充搜索词" /></label>
        <label v-else class="research-field research-keyword"><span>批量关键词</span><UTextarea v-model="batchKeywords" :rows="2" :disabled="!canPermission('xhsResearch:create') || (submitting)" maxlength="1620" placeholder="每行一个关键词，最多 20 行" aria-label="批量采集关键词" /></label>
      </div>
      <p v-if="accountError" class="account-hint" role="alert">{{ accountError }}</p>
      <div v-if="showAdvanced" id="xhs-advanced-fields" class="research-fields advanced-fields">
        <label class="research-field"><span>发布时间</span><USelect :disabled="!canPermission('xhsResearch:create')" v-model="form.period" :items="periodOptions" aria-label="发布时间范围" /></label>
        <label class="research-field"><span>排序方式</span><USelect :disabled="!canPermission('xhsResearch:create')" v-model="form.sort_by" :items="sortOptions" aria-label="排序方式" /></label>
        <label class="research-field"><span>采集数量</span><USelect :disabled="!canPermission('xhsResearch:create')" v-model="form.note_limit" :items="limitOptions" aria-label="采集笔记上限" /></label>
      </div>
      <div class="research-actions">
        <div class="collection-summary">
          <strong>将搜索：{{ form.grade }} {{ form.subject }} {{ batchMode ? '多关键词队列' : form.keyword || '全部知识点' }}</strong>
          <div class="collection-options"><span>{{ periodLabels[form.period] }} · {{ sortLabel(form.sort_by) }} · 每项最多 {{ form.note_limit }} 条</span><UCheckbox v-model="batchMode" label="批量关键词队列" :disabled="!canPermission('xhsResearch:create') || (submitting)" /></div>
        </div>
        <UButton v-if="canAdmin('xhsResearch', 'run')" type="submit" :label="batchMode ? '创建队列并采集第一项' : '开始采集'" icon="i-lucide-play" :title="collectionHint" :loading="submitting" :disabled="!canCollect" />
      </div>
      <p v-if="!canCollect" class="collection-readiness" role="status">{{ collectionHint }}</p>
    </form>
    <section v-if="batch" class="queue-panel panel-card" aria-label="多关键词采集队列">
      <div class="panel-heading"><h3>采集队列 <span class="count-pill">{{ batch.items.filter(item => item.status === 'completed').length }} / {{ batch.items.length }}</span></h3><div class="queue-buttons"><USelect :model-value="batch.id" :items="batches.map(item => ({ value: item.id, label: `${compactDate(item.created_at)} · ${item.completed}/${item.total} 项` }))" aria-label="历史采集队列" :disabled="submitting" @update:model-value="chooseBatch(String($event))" /><UButton v-if="queueRunning" :label="pauseRequested ? '本项完成后暂停' : '暂停队列'" size="sm" color="neutral" :disabled="pauseRequested" @click="pauseRequested = true" /><UButton v-permission="'xhsResearch:run'" v-else label="采集下一项 / 重试失败项" icon="i-lucide-play" size="sm" :disabled="!queueRemaining || !bridgeReady || collectorBusy || submitting" @click="runQueue" /></div></div>
      <div class="queue-items"><span v-for="item in batch.items" :key="item.id" :class="'status-' + item.status">{{ item.keyword }} · {{ statusLabels[item.status] }} · {{ taskAccountName(item) }}</span></div>
      <p>每次点击只采集下一项，保存后自动暂停，不连续运行全部关键词。相同账号和条件在 10 分钟内复用已有快照，保留原采集时间。</p>
    </section>
    <div v-if="progress" class="collection-progress" role="status" aria-live="polite"><div><strong>{{ accountName(actionAccount) }} · {{ selectedTask?.grade }}{{ selectedTask?.subject }} {{ selectedTask?.keyword }}</strong><span>{{ progressLabels[progress.stage] }} · {{ progress.collected }} / {{ progress.total }} 条</span></div><progress :value="progress.collected" :max="progress.total" /></div>

    <details class="research-boundary"><summary>采集范围说明</summary><p>只保存页面可见的标题、作者、发布时间和点赞数快照，不采集评论，也不会点赞、关注或发布内容。<a :href="selectedTask ? researchSearchUrl(selectedTask) : 'https://www.xiaohongshu.com/explore'" target="_blank" rel="noreferrer">打开小红书</a></p></details>

    <div class="research-content-grid">
      <section class="research-history panel-card" aria-label="采集历史">
        <div class="panel-heading">
          <div><h3>采集历史 <span class="count-pill">{{ taskTotal }}</span></h3></div>
          <UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" size="xs" aria-label="刷新采集历史" :loading="loading" @click="refresh" />
        </div>
        <div v-if="!tasks.length" class="empty-state">{{ loading ? '正在加载任务...' : '完成第一次采集后，历史快照会显示在这里。' }}</div>
        <div v-else class="task-list">
          <button v-for="task in tasks" :key="task.id" type="button" class="task-row" :class="{ selected: selectedTask?.id === task.id }" :aria-pressed="selectedTask?.id === task.id" @click="selectTask(task)">
            <span class="task-row-top"><span class="task-grade">{{ task.grade }} · {{ task.subject }}</span><UIcon name="i-lucide-chevron-right" class="size-4 task-chevron" /></span>
            <span class="task-keyword">{{ task.keyword || '不限知识点' }}</span>
            <span class="task-meta">{{ periodLabels[task.period] }} · {{ sortLabel(task.sort_by) }} · {{ compactDate(task.created_at) }}</span>
            <span class="task-bottom"><span class="status-tag" :class="'status-' + task.status">{{ statusLabels[task.status] }}</span><span>{{ taskAccountName(task) }} · {{ task.note_count }} 条笔记</span></span>
          </button>
        </div>
        <div v-if="taskTotal > taskPageSize" class="pagination-footer history-pagination">
          <span>第 {{ taskPage }} / {{ Math.ceil(taskTotal / taskPageSize) }} 页 · 共 {{ taskTotal }} 条</span>
          <UPagination v-model:page="taskPage" :total="taskTotal" :items-per-page="taskPageSize" :sibling-count="1" size="sm" :disabled="loading" />
        </div>
      </section>

      <section class="research-results panel-card" aria-label="采集结果">
        <div class="panel-heading result-heading">
          <div><h3>采集结果</h3><p v-if="selectedTask">{{ selectedTask.grade }} · {{ selectedTask.subject }} · {{ periodLabels[selectedTask.period] }} · {{ selectedTask.note_count }} 条笔记 · {{ taskAccountName(selectedTask) }}</p></div>
          <div class="result-tools"><UButton v-if="selectedTask" label="全部笔记" color="neutral" variant="outline" size="xs" :disabled="selectingTask" @click="selectedTask = null" /><UButton v-permission="'xhsResearch:delete'" v-if="selectedTask" label="删除记录" icon="i-lucide-trash-2" color="error" variant="ghost" size="xs" :disabled="submitting || selectingTask" :loading="deletingId === selectedTask.id" @click="removeTask(selectedTask)" /></div>
        </div>
        <p v-if="selectingTask" class="empty-state" role="status">正在读取采集结果…</p>
        <XhsNoteLibrary v-if="!selectedTask || selectedTask.status === 'completed'" v-show="!selectingTask" :admin-id="user.id" :task-id="selectedTask?.id || ''" :refresh-key="libraryRefresh" :note-account-name="selectedAccountInfo?.name || ''" :opening-note-id="openingNoteId" @open-note="viewNote" />
        <div v-else-if="selectedTask && !selectingTask" class="empty-state result-state">{{ selectedTask.status === 'running' ? '任务正在采集中。' : selectedTask.status === 'failed' ? (selectedTask.error || '本次采集失败。可重新运行任务。') : '任务等待启动。' }}
          <UButton v-permission="'xhsResearch:run'" class="mt-3" :label="selectedTask.status === 'running' ? '继续采集' : '重新运行'" icon="i-lucide-rotate-cw" size="sm" :loading="submitting" :disabled="!bridgeReady || collectorBusy" @click="runTask(selectedTask)" />
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.hero-copy p { margin:6px 0 0;color:#687f71;font-size:12px;line-height:1.6; }
.collection-summary { display:grid;gap:4px;min-width:0;font-size:11px;color:#708578; }.collection-summary strong { color:#375b47;font-weight:600;overflow-wrap:anywhere; }
.collection-options { display:flex;align-items:center;gap:12px;flex-wrap:wrap; }.collection-options > span { white-space:nowrap; }
.collection-readiness { margin:6px 0 0;color:#8b7046;font-size:11px;line-height:1.5; }
.account-field-label { display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px; }.account-field-label > span { color:#53675b;font-weight:600; }.account-field-label > div { display:flex;gap:2px; }
.account-field-label :deep(button) { padding:2px;min-height:20px; }
.result-tools { display:flex;gap:6px;flex-wrap:wrap; }
.xhs-page :is(button,a,summary):focus-visible { outline:2px solid var(--ui-primary);outline-offset:3px; }
.research-account-row { display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
.account-select { min-width:0; }
.research-account-row a { padding:8px 0; color:#247553; font-size:12px; }
.account-hint { color:#a64b42; font-size:11px; margin:6px 0 0; line-height:1.6; }
.xhs-page { padding:16px; border-color:#e4ece7; border-radius:16px; background:#f8faf9; }
.xhs-hero { display:flex; align-items:center; justify-content:space-between; gap:16px; min-height:54px; margin-bottom:12px; padding:8px 14px; border:1px solid #dcebe2; border-radius:12px; background:linear-gradient(105deg,#edf7f1,#f7faf7); }
.hero-copy { position:relative; z-index:1; }
.hero-copy h2 { margin:0; color:#173d30; font-size:18px; font-weight:700; letter-spacing:-.03em; }
.hero-controls { display:flex; align-items:center; justify-content:flex-end; gap:8px; }
.collector-state { display:flex; align-items:center; gap:8px; padding:6px 9px; border:1px solid transparent; border-radius:999px; font-size:10px; font-weight:600; white-space:nowrap; }
.collector-dot { width:8px; height:8px; border-radius:50%; background:currentColor; box-shadow:0 0 0 3px color-mix(in srgb,currentColor 13%,transparent); }
.collector-online { color:#16744f; border-color:#cbe6d5; background:#f3fbf5; }
.collector-paused { color:#7b7045; border-color:#eae3ce; background:#fffaf0; }
.collector-offline { color:#9b4c45; border-color:#efd8d5; background:#fff6f5; }
.collector-guide { margin:0 0 10px; padding:8px 12px; border:1px solid #eee5d2; border-radius:10px; background:#fffcf5; color:#74684a; font-size:11px; }
.collector-guide summary,.research-boundary summary { cursor:pointer; font-weight:600; }
.guide-copy { display:flex; flex-wrap:wrap; align-items:center; gap:7px; padding-top:8px; color:#847b67; font-size:11px; }
.guide-copy code { padding:4px 7px; border-radius:6px; background:#f2eee4; color:#625439; font-size:10px; }
.panel-card { min-width:0; border:1px solid #e5ece8; border-radius:15px; background:#fff; box-shadow:0 5px 18px rgba(32,65,49,.035); }
.research-form { display:block; margin:0; padding:13px 16px 12px; }
.batch-input { display:grid;gap:9px;margin-top:12px; }.batch-input small,.queue-panel p { color:#839088;font-size:11px; }
.queue-panel { padding:16px;margin-top:12px; }.queue-buttons { display:flex;gap:8px;align-items:center;flex-wrap:wrap; }.queue-items { display:flex;flex-wrap:wrap;gap:7px; }.queue-items > span { padding:5px 9px;border-radius:6px;font-size:11px; }
.collection-progress { padding:14px;margin-top:12px;border:1px solid #cbe6d5;border-radius:10px;background:#f3fbf5; }.collection-progress > div { display:flex;gap:12px;justify-content:space-between;font-size:12px; }.collection-progress progress { width:100%;height:7px;margin-top:10px;accent-color:#287653; }
.panel-heading { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:10px; }
.panel-heading h3 { display:flex; align-items:center; gap:9px; margin:0; color:#233b30; font-size:14px; font-weight:700; letter-spacing:-.01em; }
.panel-heading p { margin:0; color:#839088; font-size:11px; line-height:1.6; }
.research-fields { display:grid; align-items:end; gap:10px; }
.primary-fields { grid-template-columns:minmax(160px,1.25fr) minmax(90px,.65fr) minmax(85px,.6fr) minmax(180px,1.6fr); }
.advanced-fields { grid-template-columns:repeat(3,minmax(120px,1fr)); margin-top:10px; padding-top:10px; border-top:1px solid #edf1ee; }
.research-field { display:flex; min-width:0; flex-direction:column; gap:7px; color:#63766b; font-size:11px; }
.research-field > span { color:#53675b; font-weight:600; }
.research-field small { margin-left:4px; color:#99a39c; font-size:10px; font-weight:400; }
.research-actions { display:flex; align-items:center; justify-content:space-between; gap:9px; margin-top:10px; padding-top:9px; border-top:1px solid #edf1ee; }
.quiet-collection-note { color:#89958e; font-size:10px; }
.research-boundary { margin:8px 2px 14px; color:#839088; font-size:10px; line-height:1.7; }
.research-boundary p { margin:5px 0 0; }
.research-boundary a,.xhs-result-table a { display:inline-flex; align-items:center; gap:3px; margin-left:6px; color:#287653; font-weight:600; text-decoration:none; white-space:nowrap; }
.research-boundary a:hover,.xhs-result-table a:hover { text-decoration:underline; text-underline-offset:3px; }
.research-content-grid { display:grid; grid-template-columns:minmax(260px,.8fr) minmax(0,2.2fr); align-items:start; gap:16px; }
.research-history,.research-results { padding:18px; }
.research-history .panel-heading,.research-results .panel-heading { min-height:48px; margin-bottom:14px; }
.count-pill { display:inline-grid; min-width:23px; height:22px; place-items:center; padding:0 6px; border-radius:999px; background:#eef6f0; color:#548166; font-size:10px; font-weight:650; }
.task-list { display:flex; flex-direction:column; gap:8px; }
.task-row { display:flex; flex-direction:column; gap:6px; width:100%; padding:12px; border:1px solid #e8eeea; border-radius:11px; background:#fff; text-align:left; cursor:pointer; transition:border-color .16s ease,background .16s ease,transform .16s ease; }
.task-row:hover { transform:translateY(-1px); border-color:#b7d2c1; background:#fbfdfb; }
.task-row.selected { border-color:#8fbea1; background:#f3f9f5; box-shadow:inset 3px 0 #4e9368; }
.task-row-top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.task-grade { color:#2c493a; font-size:12px; font-weight:700; }
.task-chevron { color:#9aa89f; transition:transform .16s ease; }
.task-row.selected .task-chevron { transform:translateX(2px); color:#508767; }
.task-keyword { overflow:hidden; color:#607268; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.task-meta,.task-bottom { display:flex; flex-wrap:wrap; gap:6px 8px; color:#6f8275; font-size:11px; line-height:1.6; }
.task-bottom { align-items:center; padding-top:2px; }
.task-bottom > span:last-child { margin-left:auto; }
.status-tag { padding:3px 7px; border-radius:999px; background:#f0f2f1; color:#607168; font-size:11px; }
.status-completed { background:#eaf5ed; color:#33754d; }
.status-failed { background:#fbebeb; color:#ac3f3f; }
.status-running { background:#eaf2fc; color:#356a9b; }
.status-queued { background:#f2f1ec; color:#7a7155; }
.pagination-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; color:#839088; font-size:10px; }
.history-pagination { margin-top:13px; padding-top:12px; border-top:1px solid #edf1ee; }
.table-section-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:9px; }
.table-section-heading > div { display:flex; align-items:baseline; gap:8px; }
.table-section-heading h4 { margin:0; color:#334b3d; font-size:12px; font-weight:700; }
.table-section-heading span,.table-count { color:#8a968f; font-size:9px; }
.table-count { padding:4px 7px; border:1px solid #e9efeb; border-radius:999px; background:#fbfcfb; }
.xhs-table-wrap { overflow-x:auto; border:1px solid #e8eeea; border-radius:10px; }
.xhs-result-table { min-width:650px; }
.xhs-result-table th { position:sticky; top:0; z-index:1; background:#f4f8f5; color:#6d7c72; font-size:9px; }
.xhs-result-table td { color:#65746a; font-size:10px; }
.result-title { min-width:210px; max-width:370px; color:#354b3d !important; font-weight:550; }
.likes-value { color:#b66a3d !important; font-weight:650; font-variant-numeric:tabular-nums; }
.no-notes { padding:24px !important; color:#8a968f !important; text-align:center; }
.notes-pagination { margin-top:12px; }
.empty-state { display:flex; min-height:150px; flex-direction:column; align-items:center; justify-content:center; padding:20px; border:1px dashed #dfe8e2; border-radius:12px; color:#87938b; font-size:11px; text-align:center; line-height:1.7; }
.result-state { min-height:260px; }
.empty-icon { display:grid; place-items:center; width:48px; height:48px; margin-bottom:12px; border-radius:15px; background:#eff7f1; color:#699274; }
@media(max-width:1100px) { .primary-fields { grid-template-columns:minmax(150px,1.25fr) minmax(80px,.65fr) minmax(75px,.6fr) minmax(150px,1.5fr); }.research-content-grid { grid-template-columns:1fr; }.task-list { display:grid;grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(min-width:801px) and (max-width:960px) { .primary-fields { grid-template-columns:repeat(3,minmax(0,1fr)); }.research-keyword { grid-column:1/-1; } }
@media(max-width:520px) { .task-list { grid-template-columns:1fr; } }
@media(prefers-reduced-motion:reduce) { .task-row,.task-chevron { transition:none; }.task-row:hover { transform:none; } }
@media(max-width:800px) { .xhs-page { padding:12px; }.xhs-hero { padding:8px 10px; }.hero-copy h2 { font-size:17px; }.research-content-grid { grid-template-columns:1fr; }.research-form,.research-history,.research-results { padding:13px; }.primary-fields,.advanced-fields { grid-template-columns:repeat(2,minmax(100px,1fr)); }.research-keyword { grid-column:1/-1; }.research-content-grid { gap:12px; } }
@media(max-width:520px) { .queue-panel .panel-heading { flex-direction:column; align-items:stretch; gap:10px; }.queue-panel h3 { white-space:nowrap; }.queue-buttons { width:100%; } .xhs-hero { align-items:flex-start; flex-direction:column; gap:8px; }.hero-controls { width:100%; flex-wrap:wrap; justify-content:flex-start; }.collector-state { padding:5px 7px; }.primary-fields { grid-template-columns:1fr 1fr; gap:8px; }.account-select,.research-keyword { grid-column:1/-1; }.advanced-fields { grid-template-columns:1fr 1fr; gap:9px; }.research-actions { align-items:flex-start;flex-direction:column;gap:10px; }.research-actions > :deep(button) { align-self:stretch;justify-content:center; }.collection-options { gap:6px; }.pagination-footer { align-items:flex-start; flex-direction:column; } }
</style>
