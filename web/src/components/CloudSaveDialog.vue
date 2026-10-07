<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { captureWorkspaceGuard } from '../api'
import { captureSnapshot, completeArchive, createArchive, createArchiveFolder, fetchArchiveFolders } from '../library'
import type { ArchiveDetail, ArchiveFolder, ArchiveRequest, ArchiveSnapshot } from '../library'
// crypto.randomUUID 是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId } from '../../../shared/webcrypto'

const props = defineProps<{ open: boolean; selected: number }>()
const emit = defineEmits<{ close: []; busy: [value: boolean]; library: [] }>()
const store = useExamStore()
const scope = ref('current')
const folder = ref('unfiled')
const folders = ref<ArchiveFolder[]>([])
const newFolder = ref('')
const addingFolder = ref(false)
const groupName = ref('')
const mode = ref<ArchiveSnapshot['export_options']['mode']>('student')
const error = ref('')
const busy = ref(false)
const progress = ref('')
const loadingFolders = ref(true)
interface SaveJob { request: ArchiveRequest; record?: ArchiveDetail; state: 'pending' | 'saving' | 'files' | 'ready' | 'failed'; error: string }
const jobs = ref<SaveJob[]>([])
let active = true
let saveController: AbortController | undefined
const folderOptions = computed(() => [{ label: '未分类', value: 'unfiled' }, ...folders.value.map(value => ({ label: value.name, value: value.id }))])
const options = computed(() => [{ label: '当前试卷', value: 'current' }, { label: `全部 ${store.papers.length} 份`, value: 'all' }])
const allReady = computed(() => jobs.value.length > 0 && jobs.value.every(job => job.state === 'ready'))
const modes = [{ label: '学生卷', value: 'student' }, { label: '试卷与答案', value: 'withAnswers' }, { label: '仅答案', value: 'answersOnly' }]
async function loadFolders() {
  loadingFolders.value = true; error.value = ''
  try { folders.value = (await fetchArchiveFolders()).items }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '文件夹加载失败' }
  finally { loadingFolders.value = false }
}
async function addFolder() {
  if (!newFolder.value.trim() || busy.value) return
  busy.value = true; error.value = ''
  try { const created = await createArchiveFolder(newFolder.value.trim()); await loadFolders(); folder.value = created.id; addingFolder.value = false; newFolder.value = '' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '文件夹创建失败' }
  finally { busy.value = false }
}
function prepare() {
  const papers = scope.value === 'all' ? store.papers : [store.papers[props.selected] || store.papers[0]]
  const groupId = papers.length > 1 ? randomId() : ''
  jobs.value = papers.filter(Boolean).map(paper => {
    paper.archiveSourceId ||= randomId()
    return { request: { request_id: randomId(), source_id: paper.archiveSourceId,
      snapshot: captureSnapshot(paper, store.template, store.style, mode.value, store.addDayLabel),
      folder_id: folder.value === 'unfiled' ? null : folder.value,
      group_id: groupId, group_name: papers.length > 1 ? groupName.value.trim() : '' }, state: 'pending', error: '' }
  })
}
async function save() {
  if (busy.value || store.accountChanged || store.generating || store.layoutMode) return
  if (!jobs.value.length) prepare()
  busy.value = true; emit('busy', true); error.value = ''
  saveController = new AbortController()
  const assertOwner = captureWorkspaceGuard()
  const canContinue = () => active && !store.accountChanged && !saveController?.signal.aborted
  try {
    for (const [index, job] of jobs.value.entries()) {
      if (!canContinue()) break
      if (job.state === 'ready') continue
      job.error = ''
      try {
        assertOwner()
        if (!canContinue()) throw new Error('保存已停止，请刷新后查看云端试卷')
        progress.value = `正在保存第 ${index + 1}/${jobs.value.length} 份内容`
        job.state = 'saving'
        if (!job.record) job.record = await createArchive(job.request)
        assertOwner()
        if (!canContinue()) throw new Error('保存已停止，可在云端试卷中重试文件')
        job.state = 'files'
        job.record = await completeArchive(job.record, message => { progress.value = `第 ${index + 1}/${jobs.value.length} 份 · ${message}` }, canContinue, saveController.signal)
        job.state = 'ready'
      } catch (cause) { job.state = 'failed'; job.error = cause instanceof Error ? cause.message : '保存失败，请重试' }
    }
  } finally { if (saveController.signal.aborted) error.value = '保存已取消，已完成内容仍在云端；可重试未完成项'; busy.value = false; progress.value = ''; emit('busy', false) }
}
function close() { if (!busy.value) emit('close') }
function warnOnExit(event: BeforeUnloadEvent) { if (busy.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { void loadFolders(); window.addEventListener('beforeunload', warnOnExit) })
onBeforeUnmount(() => { active = false; saveController?.abort(); emit('busy', false); window.removeEventListener('beforeunload', warnOnExit) })
</script>

<template>
  <UModal :open="open" title="保存到云端" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-xl' }" @update:open="value => { if (!value) close() }">
    <template #body>
      <div class="space-y-5">
        <UAlert v-if="error" :title="error" color="error" variant="soft"><template #actions><UButton label="重试" color="error" variant="soft" @click="loadFolders" /></template></UAlert>
        <UFormField v-if="store.papers.length > 1" label="保存范围"><URadioGroup v-model="scope" :items="options" orientation="horizontal" :disabled="busy || !!jobs.length" /></UFormField>
        <UFormField label="文件夹"><div class="flex items-center gap-2"><USelect v-model="folder" :items="folderOptions" aria-label="归档文件夹" class="flex-1" :loading="loadingFolders" :disabled="busy || !!jobs.length" /><UTooltip text="新建文件夹"><UButton icon="i-lucide-folder-plus" color="neutral" variant="outline" aria-label="新建文件夹" :disabled="busy || !!jobs.length" @click="addingFolder = !addingFolder" /></UTooltip></div></UFormField>
        <div v-if="addingFolder" class="flex gap-2"><UInput v-model="newFolder" placeholder="文件夹名称" aria-label="新文件夹名称" maxlength="60" class="flex-1" :disabled="busy" @keydown.enter="addFolder" /><UButton label="创建" :loading="busy" :disabled="!newFolder.trim()" @click="addFolder" /></div>
        <UFormField v-if="scope === 'all' && store.papers.length > 1" label="分组名称（可选）"><UInput v-model="groupName" placeholder="例如：本周数学练习" aria-label="试卷分组名称" maxlength="120" class="w-full" :disabled="busy || !!jobs.length" /></UFormField>
        <UFormField label="PDF 内容"><USelect v-model="mode" :items="modes" aria-label="归档 PDF 内容" class="w-full" :disabled="busy || !!jobs.length" /></UFormField>
        <div v-if="jobs.length" class="save-results" role="status">
          <div v-for="(job, index) in jobs" :key="job.request.request_id" class="save-job"><UIcon :name="job.state === 'ready' ? 'i-lucide-circle-check' : job.state === 'failed' ? 'i-lucide-circle-alert' : 'i-lucide-loader-circle'" :class="['size-5 shrink-0', job.state === 'ready' ? 'text-primary' : job.state === 'failed' ? 'text-warning' : 'text-muted animate-spin']" /><div class="min-w-0"><p class="text-sm break-words">{{ job.request.snapshot.paper.title || '第 ' + (index + 1) + ' 份试卷' }}</p><p class="mt-1 text-xs text-muted break-words">{{ job.state === 'ready' ? '已归档 · v' + job.record?.version + ' · ' + (job.record?.folder_name || '未分类') : job.record ? '内容已保存，文件未完成' : job.state === 'failed' ? '内容未保存' : '正在保存' }}</p><p v-if="job.error" class="mt-1 text-xs text-warning break-words">{{ job.error }}</p></div></div>
        </div>
        <p v-if="progress" class="text-xs text-primary" role="status">{{ progress }}</p>
      </div>
    </template>
    <template #footer>
      <UButton v-if="busy" label="取消保存" color="neutral" variant="outline" @click="saveController?.abort()" />
      <UButton :label="allReady ? '完成' : '关闭'" color="neutral" variant="outline" :disabled="busy" @click="close" />
      <UButton v-if="allReady" icon="i-lucide-library" label="查看云端试卷" @click="emit('library')" />
      <UButton v-else icon="i-lucide-cloud-upload" :label="jobs.length ? '重试未完成项' : '保存试卷'" :loading="busy" :disabled="busy || loadingFolders || store.accountChanged" @click="save" />
    </template>
  </UModal>
</template>

<style scoped>
.save-results { border-top: 1px solid var(--ui-border-muted); }
.save-job { display: flex; gap: 10px; padding: 14px 0; border-bottom: 1px solid var(--ui-border-muted); }
</style>
