<script setup lang="ts">
import EditorPanel from './EditorPanel.vue'
import { useDialogDraft } from '../dialog-draft'
import { useRevisionConflict } from '../revision-conflict'
import { computed, ref, watch } from 'vue'
import { attachImportedEdition, catalogDetail, type CatalogDetail, type CatalogPaper } from '../catalog'
import { editionSources, saveEdition, type EditionSource } from '../growth'
import { inspectPdf } from '../catalog-import-queue'
const props = defineProps<{ open: boolean; target: CatalogPaper | null; adminId: number; inline?: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const detail = ref<CatalogDetail | null>(null), sources = ref<EditionSource[]>([])
const loose = ref(false)
const uploadFile = ref<File | null>(null)
const fileRevision = ref(0)
const mode = ref<'link' | 'upload'>('link'), checking = ref(false), progress = ref(0)
async function chooseFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  uploadFile.value = null; error.value = ''; progress.value = 0
  if (!file) return
  const current = sequence; checking.value = true
  try { await inspectPdf(file); if (current === sequence) uploadFile.value = file }
  catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '文件校验失败' }
  finally { checking.value = false }
}
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), q = ref(''), editionKind = ref<'student' | 'answers'>('answers'), sourceId = ref('none'), confirmed = ref(false)
const recovery = useRevisionConflict(detail, catalogDetail, error)

const panelBusy = computed(() => busy.value || checking.value)
const draft = useDialogDraft(computed({ get: () => props.open, set: value => { if (!value) emit('close') } }), () => [editionKind.value, sourceId.value, mode.value, confirmed.value, uploadFile.value?.name, uploadFile.value?.lastModified], panelBusy, '打印版本')
function reconcile(latest: CatalogDetail) { if (detail.value?.id === latest.id) { const clean = !draft.dirty.value; detail.value = latest; if (clean) { rebuildChoices(); setEditionSelection(); draft.markSaved() } } }
defineExpose({ busy: panelBusy, dirty: draft.dirty, canLeave: draft.canLeave, reconcile })
let sequence = 0
const sourceChoices = ref<{ value: string; label: string }[]>([])
function rebuildChoices() {
  const candidates = loose.value ? sources.value : sources.value.filter(item => editionKind.value === 'student' ? item.mode === 'student' : ['answersOnly', 'withAnswers'].includes(item.mode))
  sourceChoices.value = [{ value: 'none', label: '不关联额外文件' }, ...candidates.map(item => ({
    value: item.id,
    label: `${item.title} · v${item.version} · ${item.mode === 'student' ? '练习版' : item.mode === 'answersOnly' ? '答案版' : '习题与答案版'}${item.owned_by ? `（已单独建条目「${item.owned_by}」，需先删除该条目）` : ''}`,
  }))]
}
function setEditionSelection() {
  const selected = detail.value?.editions?.find(item => item.kind === editionKind.value)
  sourceId.value = selected?.paper_id || 'none'
  if (selected?.paper_id && !sourceChoices.value.some(item => item.value === selected.paper_id)) {
    sourceChoices.value.push({ value: selected.paper_id, label: selected.label + '（当前关联）' })
  }
  confirmed.value = false; uploadFile.value = null; mode.value = 'link'; fileRevision.value++
}
async function load() {
  if (!props.open || !props.target) return
  const current = ++sequence; loading.value = true; error.value = ''
  try {
    const [paper, alternatives] = await Promise.all([catalogDetail(props.target.id), editionSources(props.target.id, q.value)])
    if (current !== sequence) return
    detail.value = paper; sources.value = alternatives.items; loose.value = !!alternatives.loose; rebuildChoices(); setEditionSelection(); draft.markSaved()
  } catch (cause) { recovery.capture(cause); if (current === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, value => { sequence++; detail.value = null; sources.value = []; notice.value = ''; q.value = ''; if (value) void load() }, { immediate: true })
function changeKind(value: string) {
  if (value !== 'student' && value !== 'answers') return
  if (!draft.canLeave()) return
  editionKind.value = value; rebuildChoices(); setEditionSelection(); draft.markSaved()
}
function refresh() { if (draft.canLeave()) void load() }
async function searchSources() {
  if (!props.target || loading.value) return
  const current = sequence; loading.value = true
  try {
    const result = await editionSources(props.target.id, q.value)
    if (current !== sequence) return
    sources.value = result.items; loose.value = !!result.loose; rebuildChoices()
    if (sourceId.value !== 'none' && !sourceChoices.value.some(item => item.value === sourceId.value))
      sourceChoices.value.push({ value: sourceId.value, label: '已选择的文件（当前搜索范围外）' })
  } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '查找失败' }
  finally { if (current === sequence) loading.value = false }
}
async function save() {
  if (!detail.value || busy.value || loading.value || checking.value) return
  if (mode.value === 'upload' && !uploadFile.value) { error.value = '请先选择有效的 PDF'; return }
  const current = sequence; busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = mode.value === 'upload' && uploadFile.value ? await attachImportedEdition(props.adminId, detail.value.id, detail.value.revision, editionKind.value, uploadFile.value, value => { if (current === sequence) progress.value = value }, confirmed.value) : await saveEdition(props.adminId, detail.value.id, { revision: detail.value.revision, kind: editionKind.value, paper_id: sourceId.value === 'none' ? null : sourceId.value, confirm_publication: confirmed.value })
    if (current !== sequence) return
    detail.value.revision = result.revision; detail.value.editions = result.editions; confirmed.value = false
    rebuildChoices()
    setEditionSelection()
    draft.markSaved(); notice.value = '打印版本已保存'
    emit('saved')
  } catch (cause) { recovery.capture(cause); if (current === sequence) error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <EditorPanel :open="open" :inline="inline" :title="'打印版本 · ' + (target?.title || '')" :dismissible="!busy" :close="!busy" @update:open="draft.setOpen($event)"><template #body>
    <div class="field-stack">
      <UButton v-if="recovery.conflict.value" label="载入最新并保留我的修改" :loading="recovery.recovering.value" @click="recovery.reload" /><UAlert v-if="error" :title="error" color="error" />
      <UAlert v-if="notice" :title="notice" color="success" />
      <p v-if="loading">正在读取资料</p>
      <template v-if="detail">
        <p class="text-sm text-muted">一份资料除了原稿，还可以关联「练习版」和「答案解析版」两份 PDF，读者在小程序下载时可选择版本。工作台习题要求题目一致、导出模式匹配；手动导入的 PDF 不做内容校验（不限年级科目），内容是否配套由导入人自行确认。</p>
        <div v-for="edition in detail.editions || []" :key="edition.kind" class="actions-row"><span class="text-sm">{{ edition.label }}{{ edition.kind === 'original' ? '（当前原稿）' : '' }}</span><UButton v-if="edition.url" :href="edition.url" label="查看 PDF" variant="link" size="xs" /></div>
        <UFormField label="要配置的版本"><USelect :model-value="editionKind" @update:model-value="changeKind" :items="[{ value: 'student', label: '练习版' }, { value: 'answers', label: '答案解析版' }]" :disabled="busy" class="w-full" /></UFormField>
        <USelect v-model="mode" aria-label="文件来源" :items="[{value:'link',label:'关联已有文件'},{value:'upload',label:'上传新 PDF'}]" :disabled="busy || checking" />
        <template v-if="mode === 'link'">
        <div class="actions-row"><UInput v-model="q" placeholder="搜索匹配的归档" :disabled="busy" @keydown.enter.prevent="searchSources" /><UButton label="查找文件" variant="outline" :disabled="busy" :loading="loading" @click="searchSources" /></div>
        <UFormField hint="工作台习题从同年级、学科与题量的归档中匹配；导入的 PDF 会列出全部导入归档。最多显示 50 份，可搜索缩小范围。更换修订稿后需重新关联。"><USelect v-model="sourceId" :items="sourceChoices" :disabled="busy || loading" class="w-full" aria-label="关联打印文件" /></UFormField>
        </template>
        <UFormField v-else label="上传 PDF" hint="最多 32 MB；上传会替换所选打印版本，请核对题目与答案是否配套。"><input :key="fileRevision" type="file" accept="application/pdf,.pdf" :disabled="busy || loading || checking" @change="chooseFile" /><p v-if="checking">正在校验 PDF</p><p v-if="busy">{{ progress < 100 ? '上传进度 ' + progress + '%' : '上传完成，正在处理文件' }}</p></UFormField>
        <UCheckbox v-if="detail.status === 'published'" v-model="confirmed" label="已核对文件和现有会员权限，确认更新已发布的打印版本" :disabled="busy" />
        <UButton label="保存打印版本" :disabled="busy || loading || checking || (detail.status === 'published' && !confirmed)" :loading="busy" @click="save" />
      </template>
    </div>
  </template><template #footer><UButton label="刷新资料" color="neutral" variant="outline" :disabled="busy" @click="refresh" /><UButton label="完成" :disabled="busy" @click="draft.setOpen(false)" /></template></EditorPanel>
</template>
