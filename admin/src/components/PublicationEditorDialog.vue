<script setup lang="ts">
import { computed, reactive, ref, toRefs, watch, nextTick } from 'vue'
import { useCatalogPreview } from '../catalog-preview'
import type { CatalogDetail } from '../catalog'
import PaperMetadataDialog from './PaperMetadataDialog.vue'
import PaperEditionDialog from './PaperEditionDialog.vue'
import CatalogRevisionDialog from './CatalogRevisionDialog.vue'
import CatalogPreviewDialog from './CatalogPreviewDialog.vue'
import type { usePublicationEditor } from '../publication-editor'
import type { CatalogPaper } from '../catalog'
import CatalogImportQueue from './CatalogImportQueue.vue'
import ImagePdfComposer from './ImagePdfComposer.vue'
import DownloadSettings from './DownloadSettings.vue'

const props = defineProps<{
  editor: ReturnType<typeof usePublicationEditor>
}>()
const emit = defineEmits<{
  preview: [paper: CatalogPaper]
  metadata: [paper: CatalogPaper]
}>()
const {
  section,
  dialog,
  dirty: mainDirty,
  setDialogOpen,
  target,
  busy: editorBusy,
  saving,
  imageComposer,
  imageFields,
  importQueue,
  form,
  sourceQuery,
  sources,
  sourceId,
  sourceMore,
  sourceLoading,
  sourceItems,
  mode,
  gradeOptions,
  subjectOptions,
  dictionaryError,
  categoryError,
  dictionaryLoading,
  categoryLoading,
  categories,
  publishing,
  importing,
  valid,
  accessOptions,
  statuses,
  answerReadiness,
  dialogError,
  dialogNotice,
  editConflict,
  loadCategories,
  loadDictionaryOptions,
  loadSources,
  save,
  reloadEdited,
  runImport,
} = toRefs(props.editor)
const displayCategories = computed(() => {
  const current = props.editor.filterCategories.find(item => item.value === form.value.category_id)
  return current && !categories.value.some(item => item.value === current.value) ? [...categories.value, current] : categories.value
})
const publicationHints = computed(() => {
  const metadata = target.value || sources.value.find(item => item.id === sourceId.value) || imageFields.value
  const title = form.value.title.trim()
  const fullGrade = metadata.grade || ''
  const subject = metadata.subject || ''
  const grade = fullGrade.replace(/^(小学|初中|高中)/, '')
  const hints: string[] = []
  if (grade && !title.includes(grade)) hints.push('标题建议写明年级')
  if (subject && !title.includes(subject)) hints.push('标题建议写明学科')
  const theme = title.replace(fullGrade, '').replace(grade, '').replace(subject, '').replace(/[\s·・—_\-：:（）()]+/g, '')
  if (!theme) hints.push('请补充具体主题，方便家长辨认资料')
  if (!form.value.description.trim()) hints.push('建议补充简介，说明练习内容和适用场景')
  return hints
})
const previewState = reactive(useCatalogPreview())
const previewVisible = ref(false)
type Panel = { busy: boolean; dirty: boolean; canLeave: () => boolean; reconcile: (latest: CatalogDetail) => void }
const metadataPanel = ref<Panel | null>(null), editionPanel = ref<Panel | null>(null), revisionPanel = ref<Panel | null>(null)
const syncing = ref(false)
const busy = computed(() => editorBusy.value || syncing.value || [metadataPanel.value, editionPanel.value, revisionPanel.value].some(panel => panel?.busy))
const dirty = computed(() => mainDirty.value || [metadataPanel.value, editionPanel.value, revisionPanel.value].some(panel => panel?.dirty))
const visited = ref<string[]>([])
watch([() => props.editor.dialog, () => props.editor.target?.id], () => {
  visited.value = []
  previewVisible.value = false
  previewState.previewOpen = false
}, { immediate: true })
watch(previewVisible, visible => {
  if (visible && props.editor.target) void previewState.showPreview(props.editor.target)
})
watch([() => props.editor.dialog, () => props.editor.section, () => props.editor.target?.id], () => {
  if (props.editor.dialog && props.editor.target && !visited.value.includes(section.value)) visited.value.push(section.value)
}, { immediate: true })
watch(() => props.editor.target?.revision, () => {
  if (props.editor.dialog && props.editor.target) {
    if (previewVisible.value) void previewState.showPreview(props.editor.target, previewState.previewRole)
    if ('assets' in props.editor.target) [metadataPanel.value, editionPanel.value, revisionPanel.value].forEach(panel => panel?.reconcile(props.editor.target as CatalogDetail))
  }
})
function closeEditor(open: boolean) {
  if (!open && busy.value) return
  if (!open && ![metadataPanel.value, editionPanel.value, revisionPanel.value].every(panel => !panel || panel.canLeave())) return
  setDialogOpen.value(open)
}
async function childSaved() {
  syncing.value = true
  try {
    const latest = await props.editor.refreshTarget()
    if (latest) [metadataPanel.value, editionPanel.value, revisionPanel.value].forEach(panel => panel?.reconcile(latest))
  } catch (cause) { props.editor.dialogError = cause instanceof Error ? cause.message : '更新预览失败，请重试' }
  finally { syncing.value = false }
}
async function publish() {
  section.value = 'details'
  form.value.status = 'published'
  await nextTick()
  document.getElementById('publication-review')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}
const sourceModes = [
  { label: '工作台习题', value: 'source', icon: 'i-lucide-notebook-pen' },
  { label: '导入 PDF', value: 'import', icon: 'i-lucide-file-up' },
  { label: '图片合成', value: 'images', icon: 'i-lucide-images' },
  { label: '网盘链接', value: 'link', icon: 'i-lucide-link' },
]
</script>

<template>
  <UModal
    fullscreen
    :open="dialog"
    @update:open="closeEditor"
    :title="
      target
        ? '编辑公共习题'
        : mode === 'images'
          ? '图片合成 PDF 习题'
          : mode === 'import'
            ? '导入 PDF 习题'
            : '添加习题草稿'
    "
    :description="target?.title"
    :ui="{ content: 'publication-editor', header: 'publication-editor-header', body: 'publication-editor-body', footer: 'publication-editor-footer' }"
    :dismissible="!busy"
    :close="!busy"
    ><template #body>
      <div class="publication-editor-inner">
      <div v-if="target" class="publication-editor-toolbar">
        <UTabs v-model="section" :items="[{value:'details',label:'基本与发布',icon:'i-lucide-file-pen-line'},{value:'metadata',label:'教学标签',icon:'i-lucide-tags'},{value:'editions',label:'打印版本',icon:'i-lucide-printer'},{value:'revision',label:'修订稿',icon:'i-lucide-history'}].map(tab => ({ ...tab, disabled: busy }))" :content="false" variant="link" aria-label="资料编辑步骤" :ui="{ list: 'gap-5 p-0', trigger: 'px-0 pb-3', leadingIcon: 'hidden sm:block size-4' }" />
        <UButton :icon="previewVisible ? 'i-lucide-panel-right-close' : 'i-lucide-panel-right-open'" :label="previewVisible ? '收起预览' : '展开预览'" :aria-expanded="previewVisible" aria-controls="publication-preview" color="neutral" variant="outline" size="sm" @click="previewVisible = !previewVisible" />
      </div>
      <div class="publication-workspace" :class="{ 'with-preview': target && previewVisible }"><div class="publication-fields">
      <form v-show="section === 'details'" id="publication-form" class="field-stack" @submit.prevent="save">
        <UAlert v-if="categoryError" :title="categoryError" color="error"
          ><template #actions
            ><UButton
              label="重试加载分类"
              :loading="categoryLoading"
              @click="loadCategories" /></template
        ></UAlert>
        <UAlert
          v-if="!target && mode !== 'source' && dictionaryError"
          :title="dictionaryError"
          color="error"
          ><template #actions
            ><UButton
              label="重试加载年级与科目"
              :loading="dictionaryLoading"
              @click="loadDictionaryOptions" /></template
        ></UAlert>
        <fieldset v-if="!target" class="publication-group">
          <legend>资料来源</legend>
          <UTabs
            v-model="mode"
            :items="sourceModes.map((item) => ({ ...item, disabled: busy }))"
            :content="false"
            :ui="{ list: 'w-full grid grid-cols-2 sm:flex', indicator: 'hidden', trigger: 'flex-1 justify-center data-[state=active]:bg-primary data-[state=active]:text-inverted', label: 'whitespace-normal' }"
          />
          <UFormField
            v-if="mode === 'source'"
            label="工作台已保存的习题"
            required
            ><div class="source-search">
              <UInput
                v-model="sourceQuery"
                placeholder="搜索自己的习题"
                :disabled="busy"
                @keydown.enter.prevent="loadSources()"
              /><UButton
                icon="i-lucide-search"
                aria-label="查找源习题"
                color="neutral"
                variant="outline"
                :loading="sourceLoading"
                @click="loadSources()"
              />
            </div>
            <USelect
              v-model="sourceId"
              :items="sourceItems"
              placeholder="选择习题"
              :disabled="busy || sourceLoading"
              class="w-full mt-2" /><UButton
              v-if="sourceMore"
              label="加载更多"
              icon="i-lucide-chevron-down"
              variant="link"
              :loading="sourceLoading"
              @click="loadSources(true)" /><UButton
              v-if="!sourceLoading && !sources.length"
              href="/"
              label="前往出题工作台"
              icon="i-lucide-arrow-up-right"
              variant="link"
          /></UFormField>
          <CatalogImportQueue
            v-else-if="mode === 'import'"
            :queue="importQueue"
            :grades="gradeOptions"
            :subjects="subjectOptions"
            :categories="categories"
            :options-loading="dictionaryLoading || categoryLoading"
            @preview="emit('preview', $event)"
            @metadata="emit('metadata', $event)"
          />
          <template v-else-if="mode === 'images'">
            <ImagePdfComposer
              :composer="imageComposer"
              :disabled="saving || importQueue.busy"
            />
            <div class="image-metadata">
              <UFormField label="年级" required
                ><USelect
                  v-model="imageFields.grade"
                  :items="gradeOptions"
                  aria-label="图片习题年级"
                  placeholder="选择年级"
                  :disabled="busy || dictionaryLoading"
                  class="w-full"
              /></UFormField>
              <UFormField label="科目" required
                ><USelect
                  v-model="imageFields.subject"
                  :items="subjectOptions"
                  aria-label="图片习题科目"
                  placeholder="选择科目"
                  :disabled="busy || dictionaryLoading"
                  class="w-full"
              /></UFormField>
              <UFormField label="分类" required
                ><USelect
                  v-model="imageFields.category_id"
                  :items="categories"
                  aria-label="图片习题分类"
                  placeholder="选择分类"
                  :disabled="busy || categoryLoading"
                  class="w-full"
              /></UFormField>
            </div>
            <UFormField label="图片内容类型"
              ><USelect
                v-model="imageFields.mode"
                :items="[
                  { value: 'student', label: '仅习题（练习版）' },
                  { value: 'withAnswers', label: '习题与答案' },
                  { value: 'answersOnly', label: '仅答案（答案解析版）' },
                ]"
                aria-label="图片内容类型"
                :disabled="busy"
                class="w-full"
            /></UFormField>
            <p class="text-xs text-muted">
              合并后上传一份 PDF，最大 32
              MB。上传失败可在导入清单重试，无需重新选择图片。
            </p>
          </template>
          <div v-else-if="mode === 'link'" class="image-metadata">
            <UFormField label="年级" required
              ><USelect
                v-model="imageFields.grade"
                :items="gradeOptions"
                aria-label="网盘习题年级"
                placeholder="选择年级"
                :disabled="busy || dictionaryLoading"
                class="w-full"
            /></UFormField>
            <UFormField label="科目" required
              ><USelect
                v-model="imageFields.subject"
                :items="subjectOptions"
                aria-label="网盘习题科目"
                placeholder="选择科目"
                :disabled="busy || dictionaryLoading"
                class="w-full"
            /></UFormField>
          </div>
        </fieldset>
        <details class="quick-category"><summary>新建分类</summary><div class="actions-row mt-2"><UInput v-model="editor.categoryName" aria-label="新分类名称" placeholder="输入分类名称" maxlength="60" :disabled="editor.categoryCreating" @keydown.enter.prevent="editor.addCategory" /><UButton label="创建并选中" :loading="editor.categoryCreating" :disabled="!editor.categoryName.trim() || busy" @click="editor.addCategory" /></div></details>
        <fieldset class="publication-group">
          <legend>基本信息</legend>
          <UFormField v-if="!importing" label="公开标题" required description="建议使用“年级＋学科＋主题”，例如：一年级数学 · 20 以内加减法。请以文件实际内容为准。"
            ><UInput
              v-model="form.title"
              maxlength="240"
              :disabled="busy"
              required
          /></UFormField>
          <UFormField
            v-if="!importing"
            label="分类"
            required
            description="分类用于小程序专题与筛选，也可直接在这里新建。"
            ><USelect
              v-model="form.category_id"
              :items="displayCategories"
              placeholder="选择分类"
              :disabled="busy"
              required
              class="w-full"
          /></UFormField>
          <UFormField
            :label="importing ? '统一习题简介（应用到本次导入）' : '习题简介'"
          >
            <UTextarea
              v-model="form.description"
              maxlength="2000"
              :rows="3"
              :disabled="busy"
            />
          </UFormField>
        </fieldset>
        <fieldset v-if="target || mode !== 'import'" class="publication-group">
          <legend>下载方式</legend>
          <DownloadSettings
            v-if="target || mode !== 'import'"
            :fields="form"
            :disabled="busy"
            :link-only="!target && mode === 'link'"
          />
          <p
            v-if="
              target?.download_mode === 'external' &&
              target.file_status !== 'ready'
            "
            class="text-xs text-muted"
          >
            这份资料尚无 PDF。若要改为 PDF
            下载，请在“修订稿”中关联已就绪的原稿。
          </p>
        </fieldset>
        <UAlert
          v-if="!categoryLoading && !categoryError && !categories.length"
          color="warning"
          variant="soft"
          title="还没有可用的分类"
          description="请点击上方“新建分类”，填写名称后继续。"
        />
        <details class="advanced-settings" :open="publishing"><summary>高级设置：访问权限</summary><fieldset class="publication-group">
          <legend>访问权限</legend>
          <UFormField label="完整原稿观看"
            ><USelect
              v-model="form.view_access"
              :items="accessOptions"
              :disabled="busy"
              class="w-full"
          /></UFormField>
          <UFormField label="下载 / 获取链接权限"
            ><USelect
              v-model="form.download_access"
              :items="accessOptions"
              :disabled="busy || form.view_access === 'vip'"
              class="w-full"
          /></UFormField>
          <p v-if="target" class="text-sm text-muted">
            当前已保存权限：{{
              target.required_view === 'vip' ? '仅 VIP 可看' : '所有人可看'
            }}
            ·
            {{
              target.required_download === 'vip'
                ? '仅 VIP 可下载'
                : '登录后可下载'
            }}。{{
              target.question_types?.length
                ? ''
                : '此资料无可继承题型；请选择明确的观看和下载权限。'
            }}
          </p>
        </fieldset>
        </details>
        <fieldset v-if="target" id="publication-review" class="publication-group">
          <legend>发布与复核</legend>
          <UFormField label="发布状态"
            ><USelect
              v-model="form.status"
              :items="statuses.slice(1)"
              :disabled="busy"
              class="w-full"
          /></UFormField>
          <USwitch v-model="form.featured" label="优先展示" :disabled="busy" />
          <UAlert
            v-if="publishing"
            color="warning"
            variant="soft"
            title="发布后，习题、答案和文件按所设权限提供给小程序用户。请确认拥有发布权限且不含学生隐私。"
          />
          <UAlert
            v-if="publishing && publicationHints.length"
            color="info"
            variant="soft"
            title="发布前完善资料信息"
            :description="publicationHints.join('；') + '。这些建议不影响保存或发布。'"
          />
          <p v-if="target" class="text-sm text-muted">
            内容复核：{{ target.reviewed_at ? '已记录人工确认' : '尚未记录' }} ·
            答案文件：{{
              answerReadiness[target.answer_readiness || 'unknown']
            }}。导入题量为申报值，请与文件逐页核对。
          </p>
          <UCheckbox
            v-if="target"
            v-model="form.confirm_publication"
            label="已核对内容，确认公开发布"
            :disabled="busy"
          />
        </fieldset>
        <UAlert
          v-if="dialogNotice"
          :title="dialogNotice"
          color="success"
          variant="soft"
        /><UButton
          v-if="editConflict"
          label="载入最新并保留我的修改"
          @click="reloadEdited"
        /><UAlert
          v-if="dialogError"
          :title="dialogError"
          color="error"
          variant="soft"
        /></form>
      <PaperMetadataDialog v-if="dialog && visited.includes('metadata')" v-show="section === 'metadata'" ref="metadataPanel" :open="dialog" inline :target="target" :admin-id="editor.userId" @close="section = 'details'" @saved="childSaved" />
      <PaperEditionDialog v-if="dialog && visited.includes('editions')" v-show="section === 'editions'" ref="editionPanel" :open="dialog" inline :target="target" :admin-id="editor.userId" @close="section = 'details'" @saved="childSaved" />
      <CatalogRevisionDialog v-if="dialog && visited.includes('revision')" v-show="section === 'revision'" ref="revisionPanel" :open="dialog" inline :target="target" :admin-id="editor.userId" @close="section = 'details'" @saved="childSaved" />
      </div><aside v-if="target && previewVisible" id="publication-preview" class="publication-preview" aria-label="已保存资料预览"><div class="row-between mb-5"><h3>已保存内容预览</h3><UTooltip text="刷新预览"><UButton icon="i-lucide-refresh-cw" aria-label="刷新预览" size="xs" color="neutral" variant="ghost" @click="previewState.showPreview(target, previewState.previewRole)" /></UTooltip></div><CatalogPreviewDialog :state="previewState" :busy="busy" inline @publish="publish" /></aside></div></div></template
    ><template #footer
      ><UButton
        :label="importing ? '完成并返回列表' : '关闭'"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="closeEditor(false)" /><span
        class="publication-save-state"
        :class="{ 'is-dirty': dirty }"
        role="status"
        >{{
          dirty
            ? '有未保存的修改'
            : target
              ? '已保存 · ' +
                (statuses.find((item) => item.value === target?.status)
                  ?.label || '')
              : ''
        }}</span
      ><UButton
        v-if="!target && mode === 'import' && importQueue.failed.length"
        :label="'仅重试失败项（' + importQueue.failed.length + '）'"
        color="warning"
        variant="outline"
        :disabled="
          busy ||
          !!categoryError ||
          !!dictionaryError ||
          categoryLoading ||
          dictionaryLoading
        "
        @click="runImport(true)" /><UButton
        v-if="section === 'details'"
        type="submit"
        form="publication-form"
        :label="
          publishing
            ? '确认发布'
            : target
              ? '保存更改'
              : mode === 'images'
                ? '合并图片并创建草稿'
                : mode === 'import'
                  ? '导入待处理文件（' + importQueue.pending.length + '）'
                  : '创建草稿'
        "
        icon="i-lucide-check"
        :loading="busy"
        :disabled="busy || !valid" /></template
  ></UModal>
</template>

<style scoped>
:global(.publication-editor-header) { padding:18px 32px;min-height:76px;border-bottom:1px solid #e0e9e3;background:#fff; }
:global(.publication-editor-body) { padding:0;background:#f3f6f5; }
:global(.publication-editor-footer) { padding:16px 32px;gap:12px;background:#fff;box-shadow:0 -4px 20px #183e3208; }
.publication-editor-inner { max-width:1440px;margin:0 auto;padding:0 32px 32px; }
.publication-editor-toolbar { display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 0 0;position:sticky;top:0;z-index:2;background:#f3f6f5;border-bottom:1px solid #dce7df;margin-bottom:24px; }
.publication-editor-toolbar > button { margin-bottom:12px; }
.publication-workspace { min-width:0;padding-top:24px; }
.publication-editor-toolbar + .publication-workspace { padding-top:0; }
.publication-workspace.with-preview { display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:32px; }
.publication-fields { min-width:0;max-width:840px;margin:0 auto;width:100%; }
.publication-preview { min-width:0;padding:24px;background:#fff;border:1px solid var(--ui-border);border-radius:14px;box-shadow:var(--admin-shadow);align-self:start;position:sticky;top:90px;max-height:calc(100dvh - 270px);overflow:auto;animation:admin-reveal .25s ease both; }
.publication-preview h3 { font-size:13px;font-weight:600; }
.quick-category summary { cursor:pointer;font-size:13px;color:var(--ui-primary); }
.quick-category { padding:12px 16px;background:#eaf3ee;border:1px dashed #bfd5c6;border-radius:10px; }
.advanced-settings { padding:16px 20px;background:#fff;border:1px solid var(--ui-border);border-radius:12px;font-size:13px; }
.advanced-settings[open] > summary { margin-bottom:20px;color:var(--ui-primary); }
@media(max-width:800px) { .publication-workspace.with-preview { grid-template-columns:1fr; }.publication-preview { position:static;max-height:none; }.publication-editor-toolbar { flex-wrap:wrap;gap:8px;padding-top:12px; }.publication-editor-toolbar > :first-child { width:100%; }.publication-editor-inner { padding:0 16px 24px; }:global(.publication-editor-header), :global(.publication-editor-footer) { padding:14px 16px; }.publication-save-state { min-width:90px; } }

.publication-group {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  margin: 0;
  padding: 22px;
  border: 1px solid #e0e9e3;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 8px #183e3204;
}
.publication-group legend {
  padding: 0 8px;
  color: #345d49;
  font-size: 14px;
  font-weight: 600;
}
.publication-save-state {
  flex: 1;
  font-size: 12px;
  color: var(--ui-text-muted);
  overflow-wrap: anywhere;
}
.publication-save-state:not(:empty)::before { content:'';display:inline-block;width:6px;height:6px;margin-right:7px;background:#308462;border-radius:50%;vertical-align:middle; }
.publication-save-state.is-dirty { color:#987220; }
.publication-save-state.is-dirty::before { background:#b58c32; }
.image-metadata {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .publication-group { padding:16px; }
  .advanced-settings { padding:14px; }
  .image-metadata {
    grid-template-columns: 1fr;
  }
}
.source-search {
  display: flex;
  gap: 8px;
}
.source-search > :first-child {
  flex: 1;
  min-width: 0;
}
@media (max-width: 800px) {
  .publication-preview { grid-row: 1; }
}
</style>
