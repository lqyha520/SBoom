<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { completeArchive, safeLibraryUrl, createArchiveFolder, deleteArchive, deleteArchives, previewArchiveDeletion, fetchLibraryCapacity, fetchArchive, fetchArchiveFolders, fetchArchives, patchArchive } from '../library'
import { downloadBlob } from '../../../shared/download'
import type { ArchiveDeletePreview, ArchiveDeleteResult, ArchiveFolder, ArchiveSummary } from '../library'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { publicationUrl, type ImagePublication } from '../image-publication'
import { captureWorkspaceGuard, request } from '../api'
defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const auth = useAuthStore()
const ImagePublicationDialog = defineAsyncComponent(() => import('./ImagePublicationDialog.vue'))
const publication = ref<ArchiveSummary | null>(null)
const rows = ref<ArchiveSummary[]>([])
const folders = ref<ArchiveFolder[]>([])
const q = ref('')
const folder = ref('all')
const total = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const busy = ref('')
const progress = ref('')
const error = ref('')
const pendingDelete = ref<ArchiveSummary | null>(null)
const selecting = ref(false)
const selectedIds = ref<string[]>([])
const batchPreview = ref<ArchiveDeletePreview | null>(null)
const deleteResult = ref<ArchiveDeleteResult | null>(null)
const capacity = ref<{ storage_bytes: number; storage_limit_bytes: number } | null>(null)
const deleteError = ref('')
const assertLibraryOwner = captureWorkspaceGuard()
const downloadChoice = ref<ArchiveSummary | null>(null)
const addingFolder = ref(false)
const folderName = ref('')
let sequence = 0
let active = true
let timer: ReturnType<typeof setTimeout> | undefined
const folderOptions = computed(() => [{ label: '全部文件夹', value: 'all' }, { label: '未分类', value: 'unfiled' }, ...folders.value.map(value => ({ label: value.name, value: value.id }))])
const statusLabels = { pending: '文件待上传', uploading: '文件上传中', failed: '文件未就绪', ready: '已归档' }
function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2).replace(/\.00$/, '') + ' GB'
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MB'
  return bytes ? Math.max(1, Math.ceil(bytes / 1024)) + ' KB' : '0 MB'
}
function toggleSelected(id: string, checked: boolean | 'indeterminate') {
  if (busy.value || store.accountChanged) return
  deleteResult.value = null
  if (!checked) selectedIds.value = selectedIds.value.filter(value => value !== id)
  else if (!selectedIds.value.includes(id) && selectedIds.value.length < 50) selectedIds.value.push(id)
}
function selectLoaded() {
  if (busy.value || store.accountChanged) return
  selectedIds.value = rows.value.slice(0, 50).map(row => row.id)
  deleteResult.value = null
}
async function prepareBatchDelete() {
  if (!selectedIds.value.length || busy.value || store.accountChanged) return
  busy.value = 'preview-delete'; error.value = ''; deleteError.value = ''; deleteResult.value = null
  try {
    assertLibraryOwner()
    const result = await previewArchiveDeletion([...selectedIds.value])
    assertLibraryOwner()
    if (active && !store.accountChanged) batchPreview.value = result
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '删除预览失败，请重试' }
  finally { busy.value = '' }
}
async function removeBatch() {
  if (!batchPreview.value?.deletable_count || busy.value || store.accountChanged) return
  busy.value = 'batch-delete'; deleteError.value = ''
  try {
    assertLibraryOwner()
    // 确认只针对预览中固定的 ID；服务端会再次检查引用及上传状态。
    const result = await deleteArchives(batchPreview.value.items.map(item => item.id))
    assertLibraryOwner()
    if (!active || store.accountChanged) return
    deleteResult.value = result; batchPreview.value = null; selectedIds.value = []; selecting.value = false
    await load()
  } catch (cause) {
    deleteError.value = (cause instanceof Error ? cause.message : '删除请求失败') + '。若连接中断，请先刷新列表核对结果。'
  } finally { busy.value = '' }
}
async function load(append = false) {
  if (!active || store.accountChanged || (append && (loading.value || !hasMore.value))) return
  const run = ++sequence
  loading.value = true; error.value = ''
  try {
    assertLibraryOwner()
    const [result, resultFolders, resultCapacity] = await Promise.all([
      fetchArchives(q.value, folder.value === 'all' ? '' : folder.value, append ? rows.value.length : 0),
      fetchArchiveFolders(), fetchLibraryCapacity(),
    ])
    assertLibraryOwner()
    if (run !== sequence || !active || store.accountChanged) return
    rows.value = append ? [...rows.value, ...result.items] : result.items
    if (!append) selectedIds.value = []
    total.value = result.total; hasMore.value = result.has_more
    folders.value = resultFolders.items; capacity.value = resultCapacity
  } catch (cause) { if (run === sequence) error.value = cause instanceof Error ? cause.message : '试卷库加载失败' }
  finally { if (run === sequence) loading.value = false }
}
watch([q, folder], () => { selectedIds.value = []; deleteResult.value = null; sequence++; clearTimeout(timer); loading.value = true; hasMore.value = false; timer = setTimeout(() => { void load() }, 300) })
watch(() => store.accountChanged, changed => {
  if (changed) { selectedIds.value = []; batchPreview.value = null; pendingDelete.value = null; deleteResult.value = null; sequence++ }
})
async function retry(row: ArchiveSummary) {
  if (busy.value) return
  busy.value = row.id; error.value = ''
  try {
    const record = await fetchArchive(row.id)
    await completeArchive(record, message => { progress.value = message }, () => active && !store.accountChanged)
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '文件重试失败' }
  finally { busy.value = ''; progress.value = '' }
}
async function download(row: ArchiveSummary, edition?: 'original' | 'answers') {
  if (busy.value) return
  busy.value = row.id; error.value = ''
  const assertOwner = captureWorkspaceGuard()
  try {
    const pdfs = (await fetchArchive(row.id)).assets.filter(asset => asset.kind === 'pdf')
    assertOwner()
    if (!active || store.accountChanged) return
    if (pdfs.length > 1 && !edition) { downloadChoice.value = row; return }
    const pdf = pdfs.find(asset => (asset.edition || 'original') === (edition || 'original'))
    if (!pdf) throw new Error('PDF 尚未就绪')
    const blob = await request<Blob>(safeLibraryUrl(pdf.url), undefined, 60_000, 'blob')
    assertOwner()
    if (!active || store.accountChanged) return
    if (!blob.size || blob.type !== 'application/pdf') throw new Error('下载文件无效，请刷新后重试')
    downloadBlob(blob, row.title + (pdf.edition === 'answers' ? '（答案）' : '') + '.pdf')
    downloadChoice.value = null
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '下载失败' }
  finally { busy.value = '' }
}
async function move(row: ArchiveSummary, folderId: string | null) {
  if (busy.value) return
  busy.value = row.id; error.value = ''
  try { await patchArchive(row.id, { folder_id: folderId }); await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '移动失败' }
  finally { busy.value = '' }
}
function actions(row: ArchiveSummary) {
  return [[{ label: '移动到未分类', icon: 'i-lucide-files', onSelect: () => move(row, null) },
    ...folders.value.map(item => ({ label: item.name, icon: 'i-lucide-folder', onSelect: () => move(row, item.id) }))],
  [{ label: '删除此版本', icon: 'i-lucide-trash-2', color: 'error' as const, onSelect: () => { pendingDelete.value = row } }]]
}
async function remove() {
  if (!pendingDelete.value || busy.value || store.accountChanged) return
  busy.value = pendingDelete.value.id; error.value = ''
  try { assertLibraryOwner(); await deleteArchive(pendingDelete.value.id); assertLibraryOwner(); pendingDelete.value = null; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '删除失败' }
  finally { busy.value = '' }
}
async function addFolder() {
  if (!folderName.value.trim() || busy.value) return
  busy.value = 'folder'; error.value = ''
  try { await createArchiveFolder(folderName.value.trim()); folderName.value = ''; addingFolder.value = false; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '创建失败' }
  finally { busy.value = '' }
}
function preparePublication(row: ArchiveSummary) {
  if (!busy.value && !store.accountChanged && auth.user?.role === 'admin' && row.file_status === 'ready') publication.value = row
}
function publicationSaved(paper: ImagePublication) {
  if (publication.value) publication.value.publication_id = paper.id
}
function closePublication() { publication.value = null; void load() }
function close() { if (!busy.value && !publication.value && !downloadChoice.value) emit('close') }
onMounted(() => { void load() })
onBeforeUnmount(() => { active = false; sequence++; clearTimeout(timer) })
</script>

<template>
  <UModal :open="open && !publication && !downloadChoice && !batchPreview" title="云端试卷" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-3xl' }" @update:open="value => { if (!value) close() }">
    <template #body>
      <div class="cloud-filters"><UInput v-model="q" icon="i-lucide-search" placeholder="搜索试卷或知识点" aria-label="搜索云端试卷" maxlength="120" class="flex-1" /><USelect v-model="folder" :items="folderOptions" aria-label="云端文件夹筛选" class="cloud-folder-picker" /><UTooltip text="新建文件夹"><UButton icon="i-lucide-folder-plus" aria-label="新建云端文件夹" color="neutral" variant="outline" :disabled="!!busy" @click="addingFolder = !addingFolder" /></UTooltip><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" aria-label="刷新云端试卷" color="neutral" variant="outline" :loading="loading" :disabled="!!busy" @click="load()" /></UTooltip></div>
      <div v-if="addingFolder" class="flex gap-2 mt-3"><UInput v-model="folderName" placeholder="文件夹名称" aria-label="云端文件夹名称" maxlength="60" class="flex-1" /><UButton label="创建" :loading="busy === 'folder'" :disabled="!folderName.trim()" @click="addFolder" /></div>
      <UAlert v-if="error" :title="error" color="error" variant="soft" class="mt-4" />
      <p v-if="progress" class="text-xs text-primary mt-4" role="status">{{ progress }}</p>
      <p v-if="capacity" class="text-xs text-muted mt-4" aria-label="试卷库容量">已用 {{ formatBytes(capacity.storage_bytes) }} / {{ formatBytes(capacity.storage_limit_bytes) }}，含已发布试卷文件</p>
      <UAlert v-if="deleteResult" :title="`已删除 ${deleteResult.deleted_ids.length} 份，释放 ${formatBytes(deleteResult.released_bytes)}；保留 ${deleteResult.skipped.length} 份`" color="success" variant="soft" class="mt-4" />
      <ul v-if="deleteResult?.skipped.length" class="text-xs text-muted mt-2 space-y-1" aria-label="批量删除保留结果"><li v-for="item in deleteResult.skipped" :key="item.id">{{ item.title || '试卷不可用' }}：{{ item.reason }}</li></ul>
      <div v-if="rows.length" class="batch-toolbar mt-4">
        <UButton :label="selecting ? '退出批量管理' : '批量管理'" icon="i-lucide-list-checks" color="neutral" variant="outline" :disabled="!!busy || store.accountChanged" @click="selecting = !selecting; selectedIds = []" />
        <template v-if="selecting">
          <UButton label="全选已加载（最多 50 份）" color="neutral" variant="ghost" :disabled="!!busy || loading || store.accountChanged" @click="selectLoaded" />
          <UButton label="清空选择" color="neutral" variant="ghost" :disabled="!!busy" @click="selectedIds = []" />
          <UButton :label="`删除所选（${selectedIds.length}）`" icon="i-lucide-trash-2" color="error" variant="soft" :disabled="!selectedIds.length || !!busy || loading || store.accountChanged" :loading="busy === 'preview-delete'" @click="prepareBatchDelete" />
        </template>
      </div>
      <div class="flex justify-between text-xs text-muted my-4"><span>{{ total }} 份试卷</span><span>最近保存</span></div>
      <div v-if="!rows.length" class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-cloud'" :class="['size-8', { 'animate-spin': loading }]" /><h3>{{ loading ? '正在加载' : q ? '没有匹配的试卷' : '暂无云端试卷' }}</h3></div>
      <div v-for="row in rows" :key="row.id" class="archive-row">
        <UCheckbox v-if="selecting" :model-value="selectedIds.includes(row.id)" :aria-label="'选择试卷：' + row.title" :disabled="!!busy || loading || store.accountChanged || (!selectedIds.includes(row.id) && selectedIds.length >= 50)" @update:model-value="value => toggleSelected(row.id, value)" />
        <div class="archive-thumb"><img v-if="row.thumbnail_url" :src="row.thumbnail_url" :alt="row.title + ' 预览'" loading="lazy" /><UIcon v-else name="i-lucide-file-text" class="size-5 text-muted" /></div>
        <div class="min-w-0 flex-1">
          <h3 class="text-sm font-medium break-words">{{ row.title }} <span class="text-xs text-dimmed font-normal">v{{ row.version }}</span></h3>
          <p class="mt-1 text-xs text-muted break-words">{{ row.grade }} · {{ row.subject }} · {{ row.question_count ? `${row.question_count} 题` : '题量未指定' }} · {{ row.folder_name || '未分类' }}</p>
          <p class="mt-1 text-xs text-dimmed">{{ new Date(row.created_at * 1000).toLocaleString() }}</p>
          <p v-if="row.group_name" class="mt-1 text-xs text-muted break-words">{{ row.group_name }}</p>
          <UBadge :color="row.file_status === 'ready' ? 'success' : 'warning'" variant="subtle" size="sm" class="mt-2">{{ statusLabels[row.file_status] }}{{ row.page_count ? ' · ' + row.page_count + ' 页' : '' }}</UBadge>
          <div v-if="auth.user?.role === 'admin' && row.file_status === 'ready'" class="mt-2">
            <UButton v-if="row.publication_id" label="查看小程序发布" icon="i-lucide-arrow-up-right" :href="publicationUrl(row.publication_id)" target="_blank" color="neutral" variant="link" size="sm" />
            <UButton v-else label="准备发布到小程序" icon="i-lucide-send" color="neutral" variant="outline" size="sm" :disabled="!!busy || store.accountChanged" @click="preparePublication(row)" />
          </div>
        </div>
        <div class="archive-actions"><UTooltip :text="row.file_status === 'ready' ? '下载 PDF' : '重试文件'"><UButton :icon="row.file_status === 'ready' ? 'i-lucide-download' : 'i-lucide-cloud-upload'" :aria-label="row.file_status === 'ready' ? '下载归档 PDF' : '重试归档文件'" color="neutral" variant="outline" :loading="busy === row.id" :disabled="!!busy" @click="row.file_status === 'ready' ? download(row) : retry(row)" /></UTooltip><UDropdownMenu :items="actions(row)"><UButton icon="i-lucide-ellipsis" :aria-label="'管理归档：' + row.title" color="neutral" variant="ghost" :disabled="!!busy" /></UDropdownMenu></div>
      </div>
      <div v-if="hasMore" class="flex justify-center mt-4"><UButton label="加载更多" color="neutral" variant="ghost" :loading="loading" @click="load(true)" /></div>
    </template>
    <template #footer><UButton label="关闭" :disabled="!!busy" @click="close" /></template>
  </UModal>
  <UModal :open="!!batchPreview" title="确认批量删除" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-2xl' }" @update:open="value => { if (!value && !busy) batchPreview = null }">
    <template #body>
      <template v-if="batchPreview">
        <p class="text-sm">将删除 {{ batchPreview.deletable_count }} 份试卷及其文件，预计释放 {{ formatBytes(batchPreview.reclaimable_bytes) }}。此操作无法撤销。</p>
        <p class="text-sm text-muted mt-2">公共库引用的试卷（含草稿、下架、历史修订和打印版本）及正在上传的试卷会自动保留。删除时会再次检查。</p>
        <ul class="delete-preview mt-4" aria-label="批量删除预览"><li v-for="item in batchPreview.items" :key="item.id" class="py-2 border-b border-muted"><span class="text-sm break-words">{{ item.title || '试卷不可用' }}</span><p class="text-xs mt-1" :class="item.reason ? 'text-warning' : 'text-muted'">{{ item.reason ? '保留：' + item.reason : '将删除 · ' + formatBytes(item.storage_bytes || 0) }}</p></li></ul>
      </template>
      <UAlert v-if="deleteError" :title="deleteError" color="error" variant="soft" class="mt-4" />
    </template>
    <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="!!busy" @click="batchPreview = null" /><UButton :label="`确认删除 ${batchPreview?.deletable_count || 0} 份`" color="error" :loading="busy === 'batch-delete'" :disabled="!batchPreview?.deletable_count || !!busy || store.accountChanged" @click="removeBatch" /></template>
  </UModal>
  <ImagePublicationDialog v-if="publication" :open="true" :archive="publication" @close="closePublication" @saved="publicationSaved" />
  <UModal :open="!!downloadChoice" title="选择下载文件" :description="downloadChoice?.title" :dismissible="!busy" :close="!busy" @update:open="value => { if (!value && !busy) downloadChoice = null }">
    <template #body><UAlert v-if="error" :title="error" color="error" variant="soft" /><p class="text-sm text-muted">同一套试卷的学生卷与答案分别保存，按需要选择下载。</p></template>
    <template #footer><UButton label="返回" color="neutral" variant="outline" :disabled="!!busy" @click="downloadChoice = null" /><UButton label="学生卷 PDF" icon="i-lucide-file-text" :loading="!!busy" :disabled="!!busy || store.accountChanged" @click="downloadChoice && download(downloadChoice, 'original')" /><UButton label="答案 PDF" icon="i-lucide-file-check" :loading="!!busy" :disabled="!!busy || store.accountChanged" @click="downloadChoice && download(downloadChoice, 'answers')" /></template>
  </UModal>
  <UModal :open="!!pendingDelete" title="删除归档版本" :description="'确认删除「' + (pendingDelete?.title || '') + '」的这个版本及其文件？此操作无法撤销。'" :dismissible="!busy" @update:open="value => { if (!value && !busy) pendingDelete = null }"><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="!!busy" @click="pendingDelete = null" /><UButton label="确认删除" color="error" :loading="!!busy" @click="remove" /></template></UModal>
</template>

<style scoped>
.cloud-filters { display: flex; gap: 8px; flex-wrap: wrap; }
.batch-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.delete-preview { max-height: 45vh; overflow-y: auto; }
.cloud-folder-picker { max-width: 200px; min-width: 140px; }
.archive-row { display: flex; align-items: center; gap: 16px; padding: 18px 0; border-bottom: 1px solid var(--ui-border-muted); }
.archive-thumb { width: 58px; height: 82px; flex: none; border: 1px solid var(--ui-border); background: #f8faf9; display: grid; place-items: center; }
.archive-thumb img { width: 100%; height: 100%; object-fit: contain; }
.archive-actions { display: flex; gap: 5px; }
@media (max-width: 500px) { .archive-row { gap: 10px; } .archive-actions { flex-direction: column; } .archive-thumb { width: 48px; height: 68px; } .cloud-folder-picker { max-width: 150px; } }
</style>
