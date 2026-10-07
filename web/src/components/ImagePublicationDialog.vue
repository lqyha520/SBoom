<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { captureWorkspaceGuard, ApiError } from '../api'
import { useAuthStore } from '../stores/auth'
import { useExamStore } from '../stores/exam'
import { imageWorksheetTitle, plannedImageQuestionCount, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'
import { addImagePublication, fetchPublicationCategories, publicationUrl, type ImagePublication, type ImagePublicationMeta } from '../image-publication'

const props = defineProps<{ open: boolean; images: WorksheetImage[]; params: ImageWorksheetParams }>()
const emit = defineEmits<{ close: []; saved: [paper: ImagePublication] }>()
const auth = useAuthStore(), store = useExamStore()
const owner = store.ownerId, ownerGuard = captureWorkspaceGuard()
let alive = true
const current = () => alive && store.ownerId === owner && !store.accountChanged && auth.user?.role === 'admin' && String(auth.user.id) === owner
const plannedCount = plannedImageQuestionCount(props.params.items)
const meta = ref<ImagePublicationMeta>({
  title: imageWorksheetTitle(props.params).slice(0, 240),
  grade: props.params.grade, subject: props.params.subject, category_id: '', description: '',
  keyword: props.params.keyword, question_types: props.params.items.map(item => item.game_type).join(','),
  ...(plannedCount === undefined ? {} : { question_count: plannedCount * props.images.length }),
})
const categories = ref<{ label: string; value: string }[]>([])
const loading = ref(false), categoryError = ref(''), error = ref(''), busy = ref(false), progress = ref('')
const saved = ref<ImagePublication | null>(null)
// Keep the exact PDF bytes on retry so the server can recognize an already imported file.
let pdf: Blob | null = null
const valid = computed(() => current() && !loading.value && !categoryError.value && !!meta.value.title.trim()
  && !!meta.value.grade.trim() && !!meta.value.subject.trim() && categories.value.some(item => item.value === meta.value.category_id))

async function loadCategories() {
  if (!current() || loading.value) return
  loading.value = true; categoryError.value = ''
  try {
    const result = await fetchPublicationCategories(); ownerGuard()
    if (!current()) return
    categories.value = result.items.filter(item => item.is_visible).map(item => ({ value: item.id, label: item.name }))
  } catch (cause) { if (current()) categoryError.value = cause instanceof Error ? cause.message : '分类加载失败' }
  finally { loading.value = false }
}
async function save() {
  if (busy.value || saved.value || !valid.value) return
  busy.value = true; error.value = ''; progress.value = '正在合成 PDF…'
  const metadata = { ...meta.value, title: meta.value.title.trim(), grade: meta.value.grade.trim(), subject: meta.value.subject.trim() }
  try {
    ownerGuard()
    if (!pdf) {
      const { buildWorksheetPdf } = await import('../worksheet-pdf')
      if (!current()) return
      pdf = await buildWorksheetPdf(props.images, done => { if (current()) progress.value = `正在合成 PDF：${done} / ${props.images.length} 页` }, () => !current())
    }
    ownerGuard()
    if (!current()) return
    progress.value = '正在保存到后台并生成预览…'
    const paper = await addImagePublication(pdf, metadata)
    ownerGuard()
    if (!current()) return
    saved.value = paper; emit('saved', paper)
  } catch (cause) {
    if (current()) error.value = cause instanceof ApiError && (cause.status === 0 || cause.status >= 500)
      ? '暂未确认保存结果，请先到后台查看是否已有草稿；重试会复用本次 PDF。'
      : cause instanceof Error ? cause.message : '添加失败，请重试'
  } finally { busy.value = false; progress.value = '' }
}
onMounted(loadCategories)
onBeforeUnmount(() => { alive = false })
</script>

<template>
  <UModal :open="open" title="添加到后台" description="保存为习题草稿，确认后再发布" :ui="{ content: 'max-w-lg', body: 'sm:p-6' }" :dismissible="!busy" :close="!busy" @update:open="!$event && !busy && emit('close')">
    <template #body>
      <div v-if="saved" class="space-y-4">
        <div class="publication-notice" role="status"><span class="publication-icon"><UIcon name="i-lucide-check" class="size-5" /></span><div><h3>已添加为后台习题草稿</h3><p>{{ saved.title }} · {{ saved.page_count }} 页，可前往后台预览并发布。</p></div></div>
        <UButton label="前往后台查看" icon="i-lucide-arrow-up-right" :href="publicationUrl(saved.id)" target="_blank" />
      </div>
      <form v-else id="image-publication" class="publication-form" @submit.prevent="save">
        <div class="publication-notice"><span class="publication-icon"><UIcon name="i-lucide-files" class="size-5" /></span><div><h3>{{ images.length }} 张图片 · 合并为一份 PDF</h3><p>按图片顺序保存为草稿，保留知识点、题型和计划题量。请在后台核对实际题目与答案后发布。</p></div></div>
        <UFormField label="习题标题" required><UInput v-model="meta.title" aria-label="习题标题" maxlength="240" required color="primary" variant="outline" :disabled="busy" class="w-full" /></UFormField>
        <div class="grid grid-cols-2 gap-4">
          <UFormField label="年级" required><UInput v-model="meta.grade" aria-label="习题年级" maxlength="80" required color="primary" variant="outline" :disabled="busy" class="w-full" /></UFormField>
          <UFormField label="科目" required><UInput v-model="meta.subject" aria-label="习题科目" placeholder="图片实际科目" maxlength="80" required color="primary" variant="outline" :disabled="busy" class="w-full" /></UFormField>
        </div>
        <UFormField label="分类" required><USelect v-model="meta.category_id" aria-label="习题分类" :items="categories" color="primary" variant="outline" placeholder="请选择习题分类" :loading="loading" :disabled="busy || loading" class="w-full" /></UFormField>
        <UAlert v-if="categoryError" :title="categoryError" color="error" variant="soft" :actions="[{ label: '重新加载分类', onClick: loadCategories }]" />
        <p v-else-if="!loading && !categories.length" class="text-sm text-muted">暂无可用分类，请先<UButton label="前往后台添加分类" href="/admin/#categories" target="_blank" variant="link" /><UButton label="刷新分类" variant="link" @click="loadCategories" /></p>
        <UFormField label="习题说明（选填）"><UTextarea v-model="meta.description" aria-label="习题说明" maxlength="2000" :rows="3" color="primary" variant="outline" placeholder="简要说明练习内容或适用场景" :disabled="busy" class="w-full" /></UFormField>
        <p v-if="progress" role="status" class="text-sm text-muted">{{ progress }}</p>
        <UAlert v-if="error" :title="error" color="error" variant="soft"><template #actions><UButton label="查看后台习题" href="/admin/#papers" target="_blank" variant="link" /></template></UAlert>
      </form>
    </template>
    <template #footer>
      <UButton :label="saved ? '完成' : '取消'" color="neutral" variant="outline" :disabled="busy" @click="emit('close')" />
      <UButton v-if="!saved" label="保存为习题草稿" color="primary" variant="solid" icon="i-lucide-folder-plus" type="submit" form="image-publication" :loading="busy" :disabled="!valid || busy" />
    </template>
  </UModal>
</template>

<style scoped>
.publication-form { display:flex;flex-direction:column;gap:20px; }
.publication-notice { display:flex;align-items:flex-start;gap:12px;padding:14px 16px;border:1px solid var(--ui-border);border-radius:10px;background:var(--ui-bg-muted); }
.publication-icon { display:grid;place-items:center;flex-shrink:0;width:36px;height:36px;border-radius:9px;background:color-mix(in srgb,var(--ui-primary) 8%,var(--ui-bg));color:var(--ui-primary); }
.publication-notice h3 { margin:0;font-size:13px;font-weight:600;line-height:1.6;color:var(--ui-text-highlighted); }
.publication-notice p { margin:4px 0 0;font-size:12px;line-height:1.75;color:var(--ui-text-muted);overflow-wrap:anywhere; }
</style>
