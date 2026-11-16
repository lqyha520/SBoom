<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError, captureWorkspaceGuard } from '../api'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { fetchArchiveFolders, type ArchiveFolder, type ArchiveSummary } from '../library'
import { imageWorksheetTitle, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'
import { imageCloudRequestId, saveImageArchive } from '../image-cloud'

const props = defineProps<{ open: boolean; images: WorksheetImage[]; params: ImageWorksheetParams }>()
const emit = defineEmits<{ close: []; library: []; saved: [record: ArchiveSummary] }>()
const store = useExamStore(), auth = useAuthStore()
const owner = store.ownerId, ownerGuard = captureWorkspaceGuard()
let alive = true
const current = () => alive && store.ownerId === owner && !store.accountChanged && String(auth.user?.id) === owner
const title = ref(imageWorksheetTitle(props.params).slice(0, 240))
const folder = ref('unfiled'), folders = ref<ArchiveFolder[]>([])
const folderLoading = ref(false), folderError = ref('')
const busy = ref(false), error = ref(''), progress = ref('')
const saved = ref<ArchiveSummary | null>(null)
const folderOptions = computed(() => [{ label: '未分类', value: 'unfiled' }, ...folders.value.map(item => ({ label: item.name, value: item.id }))])
const valid = computed(() => current() && !!title.value.trim() && !!props.images.length && !folderLoading.value)
let pdf: Blob | null = null
let controller: AbortController | undefined

async function loadFolders() {
  if (!current() || folderLoading.value) return
  folderLoading.value = true; folderError.value = ''
  try {
    const result = await fetchArchiveFolders(); ownerGuard()
    if (current()) folders.value = result.items
  } catch (cause) { if (current()) folderError.value = cause instanceof Error ? cause.message : '文件夹加载失败' }
  finally { folderLoading.value = false }
}
async function save() {
  if (busy.value || saved.value || !valid.value) return
  busy.value = true; error.value = ''; progress.value = '正在整理图片…'
  controller = new AbortController()
  const archiveTitle = title.value.trim(), folderId = folder.value === 'unfiled' ? null : folder.value
  try {
    const requestId = await imageCloudRequestId(props.images)
    ownerGuard()
    if (!current()) return
    if (!pdf) {
      const { buildWorksheetPdf } = await import('../worksheet-pdf')
      pdf = await buildWorksheetPdf(props.images, done => { if (current()) progress.value = `正在整理图片：${done} / ${props.images.length} 张` }, () => !current())
    }
    ownerGuard()
    if (!current()) return
    progress.value = '正在上传到云端并生成预览…'
    const record = await saveImageArchive(pdf, requestId, archiveTitle, props.params, props.images.length, folderId, controller.signal)
    ownerGuard()
    if (!current()) return
    saved.value = record; emit('saved', record)
  } catch (cause) {
    if (current()) error.value = cause instanceof ApiError && (cause.status === 0 || cause.status >= 500)
      ? '暂未确认保存结果，可先查看云端试卷，或重试本次保存；同一批图片不会重复归档。'
      : cause instanceof Error ? cause.message : '云端保存失败，请重试'
  } finally { busy.value = false; progress.value = '' }
}
function warnOnExit(event: BeforeUnloadEvent) { if (busy.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { void loadFolders(); window.addEventListener('beforeunload', warnOnExit) })
onBeforeUnmount(() => { alive = false; controller?.abort(); window.removeEventListener('beforeunload', warnOnExit) })
</script>

<template>
  <UModal :open="open" title="图片保存到云端" description="先保存，之后随时准备小程序发布" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-lg' }" @update:open="!$event && !busy && emit('close')">
    <template #body>
      <div v-if="saved" class="space-y-4">
        <UAlert title="已保存到云端" :description="`${saved.title} · ${saved.page_count} 页`" icon="i-lucide-cloud-check" color="success" variant="soft" />
        <p class="text-sm text-muted">可在云端试卷中查看和下载。{{ auth.user?.role === 'admin' ? '需要公开时，点击「准备发布到小程序」，确认分类后前往后台发布。' : '资料保存在当前账号下，小程序发布由管理员操作。' }}</p>
        <UButton label="查看云端试卷" icon="i-lucide-library" @click="emit('library')" />
      </div>
      <form v-else id="image-cloud-save" class="space-y-5" @submit.prevent="save">
        <UAlert :title="`${images.length} 张图片 · 保存为一份云端 PDF`" description="按本批图片顺序保存，保留完整画面，支持之后下载和发布到小程序。" color="neutral" variant="soft" />
        <UFormField label="云端标题" required><UInput v-model="title" aria-label="云端图片标题" maxlength="240" :disabled="busy" class="w-full" /></UFormField>
        <p class="text-sm text-muted">{{ params.grade }} · {{ params.subject }}{{ params.keyword ? ` · ${params.keyword}` : '' }}</p>
        <UFormField label="保存文件夹"><USelect v-model="folder" aria-label="图片云端文件夹" :items="folderOptions" :loading="folderLoading" :disabled="busy || folderLoading" class="w-full" /></UFormField>
        <UAlert v-if="folderError" :title="folderError" description="仍可保存到未分类，或重试加载文件夹。" color="warning" variant="soft" :actions="[{ label: '重新加载文件夹', onClick: loadFolders }]" />
        <p v-if="progress" role="status" class="text-sm text-primary">{{ progress }}</p>
        <UAlert v-if="error" :title="error" color="error" variant="soft"><template #actions><UButton label="查看云端试卷" variant="link" @click="emit('library')" /></template></UAlert>
      </form>
    </template>
    <template #footer>
      <UButton :label="saved ? '完成' : '取消'" color="neutral" variant="outline" :disabled="busy" @click="emit('close')" />
      <UButton v-if="!saved" label="保存到云端" icon="i-lucide-cloud-upload" type="submit" form="image-cloud-save" :loading="busy" :disabled="busy || !valid" />
    </template>
  </UModal>
</template>
