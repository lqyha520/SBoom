<script setup lang="ts">
import { toRefs } from 'vue'
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
  dialog,
  dirty,
  setDialogOpen,
  target,
  busy,
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
const sourceModes = [
  { label: '工作台习题', value: 'source', icon: 'i-lucide-notebook-pen' },
  { label: '导入 PDF', value: 'import', icon: 'i-lucide-file-up' },
  { label: '图片合成', value: 'images', icon: 'i-lucide-images' },
  { label: '网盘链接', value: 'link', icon: 'i-lucide-link' },
]
</script>

<template>
  <UModal
    :open="dialog"
    @update:open="setDialogOpen"
    :title="
      target
        ? '编辑公共习题'
        : mode === 'images'
          ? '图片合成 PDF 习题'
          : mode === 'import'
            ? '导入 PDF 习题'
            : '添加习题草稿'
    "
    :ui="{ content: importing ? 'sm:max-w-5xl' : 'sm:max-w-2xl' }"
    :dismissible="!busy"
    :close="!busy"
    ><template #body>
      <form id="publication-form" class="field-stack" @submit.prevent="save">
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
            :ui="{ list: 'w-full flex-wrap', trigger: 'flex-1' }"
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
        <fieldset class="publication-group">
          <legend>基本信息</legend>
          <UFormField v-if="!importing" label="公开标题" required
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
            description="分类用于小程序专题与筛选，可在「小程序管理 › 分类管理」维护。"
            ><USelect
              v-model="form.category_id"
              :items="categories"
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
            下载，请先通过列表中的“修订”关联已就绪的原稿。
          </p>
        </fieldset>
        <UAlert
          v-if="!categoryLoading && !categoryError && !categories.length"
          color="warning"
          variant="soft"
          title="还没有可用的分类"
          description="请先到「小程序管理 › 分类管理」新建分类，再回来发布习题。"
        />
        <fieldset class="publication-group">
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
        <fieldset v-if="target" class="publication-group">
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
        /></form></template
    ><template #footer
      ><UButton
        :label="importing ? '完成并返回列表' : '关闭'"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="setDialogOpen(false)" /><span
        class="publication-save-state"
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
        :loading="busy"
        :disabled="busy || !valid" /></template
  ></UModal>
</template>

<style scoped>
.publication-group {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  margin: 0;
  padding: 16px 0 0;
  border: 0;
  border-top: 1px solid var(--ui-border);
}
.publication-group legend {
  padding-right: 12px;
  font-size: 14px;
  font-weight: 600;
}
.publication-save-state {
  flex: 1;
  font-size: 12px;
  color: var(--ui-text-muted);
  overflow-wrap: anywhere;
}
.image-metadata {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
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
</style>
