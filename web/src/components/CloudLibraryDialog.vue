<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { completeArchive, safeLibraryUrl, createArchiveFolder, deleteArchive, fetchArchive, fetchArchiveFolders, fetchArchives, patchArchive } from '../library'
import type { ArchiveFolder, ArchiveSummary } from '../library'
import { useExamStore } from '../stores/exam'
defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
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
const addingFolder = ref(false)
const folderName = ref('')
let sequence = 0
let active = true
let timer: ReturnType<typeof setTimeout> | undefined
const folderOptions = computed(() => [{ label: '全部文件夹', value: 'all' }, { label: '未分类', value: 'unfiled' }, ...folders.value.map(value => ({ label: value.name, value: value.id }))])
const statusLabels = { pending: '文件待上传', uploading: '文件上传中', failed: '文件未就绪', ready: '已归档' }
async function load(append = false) {
  if (!active || store.accountChanged || (append && (loading.value || !hasMore.value))) return
  const run = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await fetchArchives(q.value, folder.value === 'all' ? '' : folder.value, append ? rows.value.length : 0)
    if (run !== sequence) return
    rows.value = append ? [...rows.value, ...result.items] : result.items
    total.value = result.total; hasMore.value = result.has_more
    const resultFolders = await fetchArchiveFolders()
    if (run === sequence) folders.value = resultFolders.items
  } catch (cause) { if (run === sequence) error.value = cause instanceof Error ? cause.message : '试卷库加载失败' }
  finally { if (run === sequence) loading.value = false }
}
watch([q, folder], () => { sequence++; clearTimeout(timer); loading.value = true; hasMore.value = false; timer = setTimeout(() => { void load() }, 300) })
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
async function download(row: ArchiveSummary) {
  if (busy.value) return
  busy.value = row.id; error.value = ''
  try {
    const pdf = (await fetchArchive(row.id)).assets.find(asset => asset.kind === 'pdf')
    if (!pdf) throw new Error('PDF 尚未就绪')
    const link = document.createElement('a'); link.href = safeLibraryUrl(pdf.url); link.download = row.title + '.pdf'; link.click()
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
  if (!pendingDelete.value || busy.value) return
  busy.value = pendingDelete.value.id; error.value = ''
  try { await deleteArchive(pendingDelete.value.id); pendingDelete.value = null; await load() }
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
function close() { if (!busy.value) emit('close') }
onMounted(() => { void load() })
onBeforeUnmount(() => { active = false; sequence++; clearTimeout(timer) })
</script>

<template>
  <UModal :open="open" title="云端试卷" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-3xl' }" @update:open="value => { if (!value) close() }">
    <template #body>
      <div class="cloud-filters"><UInput v-model="q" icon="i-lucide-search" placeholder="搜索试卷或知识点" aria-label="搜索云端试卷" maxlength="120" class="flex-1" /><USelect v-model="folder" :items="folderOptions" aria-label="云端文件夹筛选" class="cloud-folder-picker" /><UTooltip text="新建文件夹"><UButton icon="i-lucide-folder-plus" aria-label="新建云端文件夹" color="neutral" variant="outline" :disabled="!!busy" @click="addingFolder = !addingFolder" /></UTooltip><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" aria-label="刷新云端试卷" color="neutral" variant="outline" :loading="loading" :disabled="!!busy" @click="load()" /></UTooltip></div>
      <div v-if="addingFolder" class="flex gap-2 mt-3"><UInput v-model="folderName" placeholder="文件夹名称" aria-label="云端文件夹名称" maxlength="60" class="flex-1" /><UButton label="创建" :loading="busy === 'folder'" :disabled="!folderName.trim()" @click="addFolder" /></div>
      <UAlert v-if="error" :title="error" color="error" variant="soft" class="mt-4" />
      <p v-if="progress" class="text-xs text-primary mt-4" role="status">{{ progress }}</p>
      <div class="flex justify-between text-xs text-muted my-4"><span>{{ total }} 份试卷</span><span>最近保存</span></div>
      <div v-if="!rows.length" class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-cloud'" :class="['size-8', { 'animate-spin': loading }]" /><h3>{{ loading ? '正在加载' : q ? '没有匹配的试卷' : '暂无云端试卷' }}</h3></div>
      <div v-for="row in rows" :key="row.id" class="archive-row"><div class="archive-thumb"><img v-if="row.thumbnail_url" :src="row.thumbnail_url" :alt="row.title + ' 预览'" loading="lazy" /><UIcon v-else name="i-lucide-file-text" class="size-5 text-muted" /></div><div class="min-w-0 flex-1"><h3 class="text-sm font-medium break-words">{{ row.title }} <span class="text-xs text-dimmed font-normal">v{{ row.version }}</span></h3><p class="mt-1 text-xs text-muted break-words">{{ row.grade }} · {{ row.subject }} · {{ row.question_count }} 题 · {{ row.folder_name || '未分类' }}</p><p class="mt-1 text-xs text-dimmed">{{ new Date(row.created_at * 1000).toLocaleString() }}</p><p v-if="row.group_name" class="mt-1 text-xs text-muted break-words">{{ row.group_name }}</p><UBadge :color="row.file_status === 'ready' ? 'success' : 'warning'" variant="subtle" size="sm" class="mt-2">{{ statusLabels[row.file_status] }}{{ row.page_count ? ' · ' + row.page_count + ' 页' : '' }}</UBadge></div><div class="archive-actions"><UTooltip :text="row.file_status === 'ready' ? '下载 PDF' : '重试文件'"><UButton :icon="row.file_status === 'ready' ? 'i-lucide-download' : 'i-lucide-cloud-upload'" :aria-label="row.file_status === 'ready' ? '下载归档 PDF' : '重试归档文件'" color="neutral" variant="outline" :loading="busy === row.id" :disabled="!!busy" @click="row.file_status === 'ready' ? download(row) : retry(row)" /></UTooltip><UDropdownMenu :items="actions(row)"><UButton icon="i-lucide-ellipsis" :aria-label="'管理归档：' + row.title" color="neutral" variant="ghost" :disabled="!!busy" /></UDropdownMenu></div></div>
      <div v-if="hasMore" class="flex justify-center mt-4"><UButton label="加载更多" color="neutral" variant="ghost" :loading="loading" @click="load(true)" /></div>
    </template>
    <template #footer><UButton label="关闭" :disabled="!!busy" @click="close" /></template>
  </UModal>
  <UModal :open="!!pendingDelete" title="删除归档版本" :description="'确认删除「' + (pendingDelete?.title || '') + '」的这个版本及其文件？此操作无法撤销。'" :dismissible="!busy" @update:open="value => { if (!value && !busy) pendingDelete = null }"><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="!!busy" @click="pendingDelete = null" /><UButton label="确认删除" color="error" :loading="!!busy" @click="remove" /></template></UModal>
</template>

<style scoped>
.cloud-filters { display: flex; gap: 8px; flex-wrap: wrap; }
.cloud-folder-picker { max-width: 200px; min-width: 140px; }
.archive-row { display: flex; align-items: center; gap: 16px; padding: 18px 0; border-bottom: 1px solid var(--ui-border-muted); }
.archive-thumb { width: 58px; height: 82px; flex: none; border: 1px solid var(--ui-border); background: #f8faf9; display: grid; place-items: center; }
.archive-thumb img { width: 100%; height: 100%; object-fit: contain; }
.archive-actions { display: flex; gap: 5px; }
@media (max-width: 500px) { .archive-row { gap: 10px; } .archive-actions { flex-direction: column; } .archive-thumb { width: 48px; height: 68px; } .cloud-folder-picker { max-width: 150px; } }
</style>
