<script setup lang="ts">
import { permissionDirective as vPermission, canPermission } from '../permissions'
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import { downloadBlob } from '../../../shared/download'
import { navigateAdmin } from '../navigation'
import {
  exportResearchNotes, getNoteHistory, listResearchNotes, markLabels, saveNoteMark,
  type LibraryNote, type NoteFilters, type NoteMarkStatus, type NoteObservation,
} from '../xhs-research'

const props = defineProps<{ adminId: number; taskId: string; refreshKey?: number; noteAccountName?: string; openingNoteId?: string }>()
const emit = defineEmits<{ openNote: [note: LibraryNote] }>()
const scope = ref(props.taskId ? 'task' : 'all')
const q = ref(''), author = ref(''), exclude = ref(''), minimum = ref(''), status = ref('all')
const hideSeen = ref(false), sort = ref<NonNullable<NoteFilters['sort']>>('likes_desc')
const page = ref(1), pageSize = 10, total = ref(0), notes = ref<LibraryNote[]>([])
const applied = ref<NoteFilters>({})
const selected = ref(new Set<string>())
const loading = ref(false), exporting = ref(false), savingId = ref(''), error = ref(''), notice = ref('')
const showMoreFilters = ref(false)
const appliedLabels = computed(() => {
  const filters = applied.value
  return [filters.q && `标题：${filters.q}`, filters.author && `作者：${filters.author}`,
    filters.min_likes !== undefined && `点赞 ≥ ${filters.min_likes}`, filters.exclude && `排除：${filters.exclude}`,
    filters.status !== undefined && filters.status !== 'all' && `标记：${markLabels[filters.status as NoteMarkStatus]}`,
    filters.hide_seen && (scope.value === 'task' ? '隐藏之前采过的笔记' : '只看采集过一次的笔记')].filter(Boolean)
})
const editor = ref<LibraryNote | null>(null), editorStatus = ref('unmarked'), editorRemark = ref(''), editorFavorite = ref(false)
const discardOpen = ref(false)
const editorDirty = computed(() => !!editor.value && (editorStatus.value !== (editor.value.mark_status || 'unmarked') || editorRemark.value !== editor.value.remark || editorFavorite.value !== editor.value.favorite))
function setEditorOpen(open: boolean) {
  if (open || savingId.value) return
  if (editorDirty.value) discardOpen.value = true
  else editor.value = null
}
const historyNote = ref<LibraryNote | null>(null), history = ref<NoteObservation[]>([]), historyPage = ref(1), historyTotal = ref(0), historyLoading = ref(false)
let requestId = 0, historyRequest = 0, active = true
const scopeOptions = computed(() => [
  ...(props.taskId ? [{ value: 'task', label: '本次采集' }] : []),
  { value: 'all', label: '全部笔记' }, { value: 'favorites', label: '我的收藏' },
])
const statusOptions = Object.entries(markLabels).map(([value, label]) => ({ value: value || 'unmarked', label }))
const allSelected = computed(() => notes.value.length > 0 && notes.value.every(note => selected.value.has(note.note_id)))
const filterValues = () => ({
  ...applied.value, task_id: scope.value === 'task' ? props.taskId : '', favorite_only: scope.value === 'favorites',
})
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
const date = (value: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'

async function load() {
  if (!active) return
  const id = ++requestId
  loading.value = true; error.value = ''
  try {
    const result = await listResearchNotes({ ...filterValues(), page: page.value, page_size: pageSize })
    if (id !== requestId) return
    total.value = result.total
    const last = Math.max(1, Math.ceil(result.total / pageSize))
    if (page.value > last) { page.value = last; return }
    notes.value = result.items
  } catch (cause) { if (id === requestId) error.value = message(cause) }
  finally { if (id === requestId) loading.value = false }
}
function apply() {
  const likes = minimum.value === '' ? undefined : Number(minimum.value)
  if (likes !== undefined && (!Number.isInteger(likes) || likes < 0 || likes > 10_000_000_000)) {
    error.value = '最低点赞数请输入非负整数'; return
  }
  applied.value = { q: q.value.trim(), author: author.value.trim(), exclude: exclude.value.trim(), min_likes: likes,
    status: status.value === 'unmarked' ? '' : status.value as NoteFilters['status'], hide_seen: hideSeen.value, sort: sort.value }
  selected.value = new Set()
  if (page.value !== 1) page.value = 1
  else void load()
}
function reset() {
  q.value = ''; author.value = ''; exclude.value = ''; minimum.value = ''; status.value = 'all'; hideSeen.value = false; sort.value = 'likes_desc'
  apply()
}
function select(id: string, checked: boolean) {
  const next = new Set(selected.value)
  if (checked) next.add(id)
  else next.delete(id)
  selected.value = next
}
function selectPage(checked: boolean) { for (const note of notes.value) select(note.note_id, checked) }
async function favorite(note: LibraryNote) {
  if (savingId.value) return
  savingId.value = note.note_id; error.value = ''
  try {
    Object.assign(note, await saveNoteMark(props.adminId, note, { favorite: !note.favorite }))
    if (scope.value === 'favorites' && !note.favorite) { select(note.note_id, false); await load() }
  } catch (cause) { error.value = message(cause) }
  finally { savingId.value = '' }
}
function edit(note: LibraryNote) {
  editor.value = { ...note }; editorStatus.value = note.mark_status || 'unmarked'; editorRemark.value = note.remark; editorFavorite.value = note.favorite
  error.value = ''
}
async function save() {
  const note = editor.value
  if (!note || savingId.value) return
  savingId.value = note.note_id; error.value = ''
  try {
    await saveNoteMark(props.adminId, note, { favorite: editorFavorite.value,
      mark_status: editorStatus.value === 'unmarked' ? '' : editorStatus.value as NoteMarkStatus, remark: editorRemark.value.trim() })
    editor.value = null; notice.value = '标记和备注已保存'; await load()
  } catch (cause) { error.value = message(cause) }
  finally { savingId.value = '' }
}
async function showHistory(note: LibraryNote) {
  historyNote.value = note; historyPage.value = 1; history.value = []; historyTotal.value = 0
  await loadHistory()
}
async function loadHistory() {
  const note = historyNote.value
  if (!note) return
  const id = ++historyRequest
  historyLoading.value = true; error.value = ''
  try {
    const result = await getNoteHistory(note.note_id, historyPage.value)
    if (id === historyRequest && historyNote.value?.note_id === note.note_id) { history.value = result.items; historyTotal.value = result.total }
  } catch (cause) { if (id === historyRequest) error.value = message(cause) }
  finally { if (id === historyRequest) historyLoading.value = false }
}
function setHistoryOpen(open: boolean) { if (!open) { historyNote.value = null; historyRequest++ } }
async function exportNotes(onlySelected: boolean) {
  if (exporting.value) return
  exporting.value = true; error.value = ''
  try {
    const blob = await exportResearchNotes(props.adminId, filterValues(), onlySelected ? [...selected.value] : undefined)
    downloadBlob(blob, `小红书${scope.value === 'favorites' ? '收藏' : '笔记'}-${new Date().toLocaleDateString('sv')}.xlsx`, 2000)
    notice.value = 'Excel 已导出'
  } catch (cause) { error.value = message(cause) }
  finally { exporting.value = false }
}
watch(scope, () => { selected.value = new Set(); page.value = 1 }, { flush: 'sync' })
watch(() => props.taskId, value => { scope.value = value ? 'task' : 'all'; selected.value = new Set(); page.value = 1 }, { flush: 'sync' })
watch(() => props.adminId, () => { editor.value = null; selected.value = new Set(); page.value = 1 }, { flush: 'sync' })
watch([page, scope, () => props.taskId, () => props.refreshKey, () => props.adminId], () => { void load() })
watch(historyPage, () => { void loadHistory() })
onActivated(() => { active = true; if (!loading.value) void load() })
const deactivate = () => { active = false; requestId++; historyRequest++; loading.value = false; historyLoading.value = false }
onDeactivated(deactivate)
onUnmounted(deactivate)
void load()
</script>

<template>
  <div class="note-library" :aria-busy="loading">
    <div class="library-toolbar">
      <div class="scope-buttons" role="group" aria-label="笔记范围"><UButton v-for="item in scopeOptions" :key="item.value" :label="item.label" :variant="scope === item.value ? 'solid' : 'ghost'" size="sm" @click="scope = item.value" /></div>
      <UButton label="刷新笔记" icon="i-lucide-refresh-cw" color="neutral" variant="ghost" size="xs" :loading="loading" @click="load" />
    </div>
    <p class="note-browser-hint">{{ noteAccountName ? '查看笔记使用「' + noteAccountName + '」的账号浏览器' : '查看笔记前，请在采集条件中选择账号。' }}</p>
    <form class="note-filters" @submit.prevent="apply">
      <UInput v-model="q" placeholder="搜索笔记标题" aria-label="搜索笔记标题" maxlength="120" />
      <UInput v-show="showMoreFilters" v-model="author" placeholder="作者" aria-label="筛选作者" maxlength="120" />
      <UInput v-show="showMoreFilters" v-model="minimum" type="number" min="0" step="1" placeholder="最低点赞数" aria-label="最低点赞数" />
      <UInput v-show="showMoreFilters" v-model="exclude" placeholder="排除词，如招生、卖课（逗号分隔）" aria-label="排除关键词" maxlength="500" />
      <USelect v-show="showMoreFilters" v-model="status" :items="[{ value: 'all', label: '全部标记' }, ...statusOptions]" aria-label="筛选选题状态" />
      <USelect v-model="sort" :items="[{ value: 'likes_desc', label: '点赞从高到低' }, { value: 'likes_asc', label: '点赞从低到高' }, { value: 'latest', label: '最近采集' }, { value: 'earliest', label: '最早采集' }]" aria-label="笔记排序" />
      <div class="filter-actions"><UButton :label="showMoreFilters ? '收起条件' : '更多条件'" icon="i-lucide-sliders-horizontal" color="neutral" variant="ghost" size="sm" :aria-expanded="showMoreFilters" @click="showMoreFilters = !showMoreFilters" /><UCheckbox v-model="hideSeen" :label="scope === 'task' ? '隐藏之前采过的笔记' : '只看采集过一次的笔记'" /><UButton label="筛选" type="submit" size="sm" :loading="loading" /><UButton label="重置" color="neutral" variant="ghost" size="sm" @click="reset" /></div>
    </form>
    <div v-if="appliedLabels.length" class="applied-filters" aria-label="已应用的笔记筛选"><span>已应用</span><span v-for="label in appliedLabels" :key="String(label)" class="applied-filter">{{ label }}</span></div>
    <UAlert v-if="error" :title="error" color="error" role="alert" />
    <p v-if="notice" class="library-notice" role="status">{{ notice }}</p>
    <div class="export-actions"><span role="status">{{ loading ? '正在读取笔记…' : total + ' 条笔记' }}<span v-if="selected.size"> · 已选 {{ selected.size }} 条（跨页保留）</span></span><div><UButton v-if="selected.size" label="取消选择" size="xs" color="neutral" variant="ghost" @click="selected = new Set()" /><UButton v-permission="'xhsResearch:export'" v-if="selected.size" :label="`导出选中 (${selected.size})`" size="xs" color="neutral" variant="outline" :loading="exporting" :disabled="loading" @click="exportNotes(true)" /><UButton v-permission="'xhsResearch:export'" label="导出筛选结果" icon="i-lucide-download" size="xs" color="neutral" variant="outline" :disabled="!total || loading" :loading="exporting" @click="exportNotes(false)" /></div></div>
    <p class="library-scroll-hint">左右滑动查看完整笔记和整理操作</p>
    <div class="data-scroll" tabindex="0" role="region" aria-label="参考笔记列表，支持横向滚动"><table class="data-table xhs-result-table"><thead><tr><th><input type="checkbox" aria-label="选择本页全部笔记" :checked="allSelected" :indeterminate="!allSelected && notes.some(note => selected.has(note.note_id))" :disabled="loading" @change="selectPage(($event.target as HTMLInputElement).checked)" /></th><th>笔记标题</th><th>作者 / 发布时间</th><th>点赞</th><th>选题整理</th><th>来源</th></tr></thead><tbody :inert="loading">
      <tr v-for="note in notes" :key="note.note_id">
        <td><input type="checkbox" :aria-label="`选择笔记：${note.title}`" :checked="selected.has(note.note_id)" @change="select(note.note_id, ($event.target as HTMLInputElement).checked)" /></td>
        <td class="note-title"><strong>{{ note.title || '（无标题）' }}</strong><div class="note-context">{{ note.grade }} · {{ note.subject }}<span v-if="note.keyword"> · {{ note.keyword }}</span></div><button v-if="note.seen_count > 1" type="button" class="seen-link" @click="showHistory(note)">{{ note.seen_before ? '之前采过 · ' : '' }}{{ note.seen_count }} 次采集记录</button><p v-if="note.remark" class="note-remark">{{ note.remark }}</p></td>
        <td>{{ note.author || '—' }}<small class="note-context">{{ note.published_text || '—' }}</small></td>
        <td class="likes-value">{{ note.likes_text || (note.likes_count ?? '—') }}<button type="button" class="history-link" :aria-label="`查看点赞记录：${note.title}`" @click="showHistory(note)">点赞记录</button></td>
        <td><div class="mark-actions"><UButton v-permission="'xhsResearch:update'" :aria-label="`${note.favorite ? '取消收藏' : '收藏笔记'}：${note.title}`" :icon="note.favorite ? 'i-lucide-star-off' : 'i-lucide-star'" :label="note.favorite ? '已收藏' : '收藏'" size="xs" :variant="note.favorite ? 'soft' : 'ghost'" :disabled="!!savingId" @click="favorite(note)" /><UButton v-permission="'xhsResearch:update'" :label="markLabels[note.mark_status]" size="xs" color="neutral" variant="outline" :aria-label="`编辑标记和备注：${note.title}`" @click="edit(note)" /></div></td>
        <td><UButton label="查看笔记" icon="i-lucide-external-link" size="xs" variant="link" :loading="openingNoteId === note.note_id" :disabled="!!openingNoteId" @click="emit('openNote', note)" /><UButton v-permission="'xhsIdeas:create'" label="转为选题" size="xs" variant="ghost" @click="navigateAdmin('xhsIdeas', { new: '1', source: note.note_id })" /></td>
      </tr>
      <tr v-if="!notes.length"><td colspan="6" class="no-notes">{{ loading ? '正在读取笔记…' : error ? '笔记暂时未能加载，请点击刷新笔记重试。' : '没有符合条件的笔记，试试重置筛选或切换到全部笔记。' }}</td></tr>
    </tbody></table></div>
    <div v-if="total > pageSize" class="library-pagination"><span>第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页 · 共 {{ total }} 条</span><UPagination v-model:page="page" :total="total" :items-per-page="pageSize" :sibling-count="1" size="sm" :disabled="loading" /></div>
    <UModal :open="!!editor" title="标记和备注" :dismissible="!savingId && !discardOpen" @update:open="setEditorOpen">
      <template #body><form id="xhs-note-mark" class="mark-form" @submit.prevent="canPermission('xhsResearch:update') && (save())"><p>{{ editor?.title }}</p><UCheckbox :disabled="!canPermission('xhsResearch:update')" v-model="editorFavorite" label="收藏这条笔记" /><USelect :disabled="!canPermission('xhsResearch:update')" v-model="editorStatus" :items="statusOptions" aria-label="笔记选题状态" /><UTextarea :disabled="!canPermission('xhsResearch:update')" v-model="editorRemark" :rows="5" maxlength="2000" placeholder="记录想借鉴的内容、改编思路或制作安排" aria-label="笔记备注" /><UAlert v-if="error" :title="error" color="error" /></form></template>
      <template #footer><UButton label="取消" color="neutral" variant="ghost" :disabled="!!savingId" @click="setEditorOpen(false)" /><UButton v-permission="'xhsResearch:update'" label="保存标记" type="submit" form="xhs-note-mark" :loading="!!savingId" /></template>
    </UModal>
    <UModal v-model:open="discardOpen" title="放弃未保存的备注？">
      <template #body><p>标记或备注尚未保存，可以继续编辑，也可以放弃这次修改。</p></template>
      <template #footer><UButton label="继续编辑" variant="outline" @click="discardOpen = false" /><UButton label="放弃修改" color="error" @click="discardOpen = false; editor = null" /></template>
    </UModal>
    <UModal :open="!!historyNote" title="历次点赞记录" @update:open="setHistoryOpen">
      <template #body><p>{{ historyNote?.title }}</p><p v-if="historyLoading">正在读取…</p><div class="history-list"><div v-for="(item, index) in history" :key="`${item.task_id}-${index}`"><strong>{{ item.likes_text || (item.likes_count ?? '未知') }} 赞</strong><span>{{ date(item.captured_at) }}</span><small>{{ item.grade }} · {{ item.subject }} · {{ item.keyword || '不限知识点' }}</small></div></div><UAlert v-if="error" :title="error" color="error" /><UPagination v-if="historyTotal > 20" v-model:page="historyPage" :total="historyTotal" :items-per-page="20" :disabled="historyLoading" /></template>
    </UModal>
  </div>
</template>

<style scoped>
.library-toolbar,.export-actions,.library-pagination { display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap; }
.note-browser-hint { margin:8px 0 0;color:#6b8072;font-size:11px;line-height:1.6; }
.scope-buttons,.export-actions > div,.mark-actions { display:flex;align-items:center;gap:6px;flex-wrap:wrap; }
.note-filters { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0;padding:14px;border-radius:10px;background:#f6f9f7; }
.filter-actions { grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap; }
.applied-filters{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0;color:var(--ui-text-muted);font-size:11px}.applied-filter{max-width:100%;padding:3px 8px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-bg-muted);overflow-wrap:anywhere}
.export-actions,.library-pagination { margin:14px 0;color:#62786a;font-size:12px; }
.library-scroll-hint { display:none; }.data-scroll:focus-visible { outline:2px solid var(--ui-primary);outline-offset:3px; }
.data-scroll { border:1px solid #e5ece8;border-radius:10px;overflow:auto; }
.xhs-result-table { min-width:720px; }
.xhs-result-table th { background:#f4f8f5;white-space:nowrap; }
.xhs-result-table td { font-size:12px; }.xhs-result-table tbody tr:hover { background:#f7faf8; }
.note-title { min-width:200px;max-width:350px; }
.note-title strong { display:block;color:#304a3c;font-size:13px;line-height:1.6; }
.note-context { display:block;margin-top:5px;color:#708075;font-size:11px; }
.note-remark { margin:6px 0 0;white-space:pre-wrap;color:#66766b;overflow-wrap:anywhere; }
.seen-link,.history-link { display:block;margin-top:5px;padding:3px 0;border:0;background:none;color:#527b63;font-size:11px;cursor:pointer;text-align:left; }
.likes-value { font-weight:650;color:#b66a3d; }
a { color:#287653;white-space:nowrap; }
.no-notes { padding:25px;text-align:center;color:#849188; }
.library-notice { color:#287653;font-size:11px; }
.mark-form { display:grid;gap:14px; }
.history-list > div { display:grid;grid-template-columns:1fr auto;gap:8px;padding:14px 0;border-bottom:1px solid #e5ece8; }
.history-list small { grid-column:1/-1;color:#849188; }
@media(max-width:900px) { .note-filters { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:800px) { .library-scroll-hint { display:block;font-size:11px;color:#6b8072;margin:8px 0; } }
@media(max-width:480px) { .note-filters { grid-template-columns:1fr; }.filter-actions { align-items:flex-start; }.export-actions { align-items:flex-start;flex-direction:column; } }
</style>
