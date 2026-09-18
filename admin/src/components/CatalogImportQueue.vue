<script setup lang="ts">
import { reactive } from 'vue'
import DownloadSettings from './DownloadSettings.vue'
import { importRowIssue, type CatalogImportQueue, type ImportRow } from '../catalog-import-queue'
import type { CatalogDetail, CatalogImportMeta } from '../catalog'
const props = defineProps<{ queue: CatalogImportQueue; grades: { label: string; value: string }[]; subjects: { label: string; value: string }[]; categories: { label: string; value: string }[]; optionsLoading: boolean }>()
const emit = defineEmits<{ preview: [paper: CatalogDetail]; metadata: [paper: CatalogDetail] }>()
const defaults = reactive({ grade: '', subject: '', category_id: '', mode: 'withAnswers' as CatalogImportMeta['mode'] })
const modes = [{ value: 'withAnswers', label: '习题与答案' }, { value: 'student', label: '仅习题（练习版）' }, { value: 'answersOnly', label: '仅答案（答案解析版）' }]
async function pick(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  input.value = ''; await props.queue.add(files, { ...defaults })
}
async function answer(row: ImportRow, event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  input.value = ''; if (file) await props.queue.setAnswer(row.id, file)
}
function applyDefaults() { props.queue.apply({ ...(defaults.grade ? { grade: defaults.grade } : {}), ...(defaults.subject ? { subject: defaults.subject } : {}), ...(defaults.category_id ? { category_id: defaults.category_id } : {}), mode: defaults.mode }) }
function status(row: ImportRow) {
  if (row.state === 'checking') return '检查文件中'
  if (row.state === 'uploading') return `上传中 ${row.progress}%`
  if (row.state === 'processing') return '上传完成，正在生成预览'
  if (row.created) return '草稿已创建'
  if (row.state === 'failed') return '导入失败'
  return row.fileError ? '文件不可用' : props.queue.stopped ? '已暂停' : '待导入'
}
</script>
<template>
  <div class="import-queue">
    <div class="batch-defaults">
      <p class="text-sm font-medium">批量填写</p>
      <div class="import-grid">
        <UFormField label="年级"><USelect v-model="defaults.grade" :items="grades" aria-label="批量年级" placeholder="选择年级" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
        <UFormField label="科目"><USelect v-model="defaults.subject" :items="subjects" aria-label="批量科目" placeholder="选择科目" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
        <UFormField label="分类"><USelect v-model="defaults.category_id" :items="categories" aria-label="批量分类" placeholder="选择分类" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
        <UFormField label="PDF 内容类型"><USelect v-model="defaults.mode" :items="modes" aria-label="批量 PDF 内容类型" :disabled="queue.busy" class="w-full" /></UFormField>
      </div>
      <p class="text-xs text-muted">内容类型只标记现有 PDF，不转换内容或生成答案。新文件使用以上设置，也可逐份修改。</p>
      <UButton label="应用到全部待导入文件" variant="outline" size="sm" :disabled="queue.busy || !queue.rows.some(row => !row.created)" @click="applyDefaults" />
    </div>
    <UFormField label="添加 PDF 文件" hint="支持多次选取；每份最多 40 页、32 MB。选取时检查格式和重复内容，页数及加密情况由服务端检查。">
      <UInput type="file" multiple accept=".pdf,application/pdf" aria-label="添加 PDF 文件" :disabled="queue.busy" @change="pick" />
    </UFormField>
    <div v-if="queue.rows.length" class="queue-summary" role="status">
      <span>共 {{ queue.rows.length }} 份 · 已创建 {{ queue.succeeded }} 份 · 失败 {{ queue.rows.filter(row => row.state === 'failed').length }} 份</span>
      <progress :value="queue.succeeded + queue.rows.filter(row => row.state === 'failed').length" :max="queue.rows.length" aria-label="导入总进度" />
      <UButton v-if="queue.running" :label="queue.stopped ? '正在停止后续导入' : '停止后续导入'" color="warning" variant="outline" size="sm" :disabled="queue.stopped" @click="queue.stop" />
      <p v-if="queue.stopped" class="text-xs text-muted">当前已上传的文件仍会处理，未开始的文件和答案附件可以稍后继续。</p>
    </div>
    <ol class="queue-rows" aria-label="导入文件清单">
      <li v-for="(row, index) in queue.rows" :key="row.id" class="queue-row" :data-row-id="row.id">
        <div class="queue-row-heading"><strong>{{ index + 1 }}. {{ row.file.name }}</strong><span>{{ (row.file.size / 1024 / 1024).toFixed(1) }} MB</span><UBadge :color="row.created ? 'success' : row.state === 'failed' || row.fileError ? 'error' : 'neutral'">{{ status(row) }}</UBadge><UButton v-if="!row.created" icon="i-lucide-x" variant="ghost" color="neutral" :aria-label="'移除第 ' + (index + 1) + ' 份文件'" :disabled="queue.busy" @click="queue.remove(row.id)" /></div>
        <template v-if="!row.created">
          <UFormField label="公开标题" required><UInput v-model="row.meta.title" maxlength="240" :aria-label="'第 ' + (index + 1) + ' 份公开标题'" :disabled="queue.busy" class="w-full" /></UFormField>
          <div class="import-grid">
            <UFormField label="年级" required><USelect v-model="row.meta.grade" :items="grades" :aria-label="'第 ' + (index + 1) + ' 份年级'" placeholder="选择年级" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
            <UFormField label="科目" required><USelect v-model="row.meta.subject" :items="subjects" :aria-label="'第 ' + (index + 1) + ' 份科目'" placeholder="选择科目" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
            <UFormField label="分类" required><USelect v-model="row.meta.category_id" :items="categories" :aria-label="'第 ' + (index + 1) + ' 份分类'" placeholder="选择分类" :disabled="queue.busy || optionsLoading" class="w-full" /></UFormField>
            <UFormField label="PDF 内容类型"><USelect v-model="row.meta.mode" :items="modes" :aria-label="'第 ' + (index + 1) + ' 份 PDF 内容类型'" :disabled="queue.busy" class="w-full" /></UFormField>
          </div>
          <DownloadSettings :fields="row.meta" :disabled="queue.busy" :label-prefix="'第 ' + (index + 1) + ' 份'" />
          <p v-if="importRowIssue(row)" class="text-sm text-error" role="alert">{{ importRowIssue(row) }}</p>
          <p v-if="row.error" class="text-sm text-error" role="alert">{{ row.error }}</p>
        </template>
        <template v-else><p class="text-sm">{{ row.created.title }}</p><div class="actions-row"><UButton label="预览并发布" size="sm" variant="outline" :disabled="queue.busy" @click="emit('preview', row.created)" /><UButton label="补充教学标签" size="sm" variant="outline" :disabled="queue.busy" @click="emit('metadata', row.created)" /></div></template>
        <details v-if="row.answerState !== 'succeeded' || row.answer" class="answer-section">
          <summary>答案 PDF（可选）{{ row.answer ? ' · ' + row.answer.name : '' }}{{ row.answerState === 'failed' ? ' · 关联失败' : row.answerState === 'succeeded' ? ' · 已关联' : '' }}</summary>
          <p class="text-xs text-muted">附上与本卷配套的答案，关联为“答案解析版”。</p>
          <UInput v-if="row.answerState !== 'succeeded'" type="file" accept=".pdf,application/pdf" :aria-label="'第 ' + (index + 1) + ' 份答案 PDF'" :disabled="queue.busy" @change="answer(row, $event)" />
          <p v-if="row.answerState === 'uploading' || row.answerState === 'processing'" role="status">{{ row.answerState === 'uploading' ? '上传答案 ' + row.answerProgress + '%' : '正在处理并关联答案' }}</p>
          <p v-if="row.answerFileError || row.answerError" class="text-sm text-error" role="alert">{{ row.answerFileError || row.answerError }}；习题草稿保留，答案可单独重试。</p>
          <div class="actions-row"><UButton v-if="row.created && row.answer && ['failed', 'queued'].includes(row.answerState)" label="关联答案（仅处理附件）" size="sm" :disabled="queue.busy || !!row.answerFileError" @click="queue.retryAnswer(row.id)" /><UButton v-if="row.answer && row.answerState !== 'succeeded'" label="移除答案附件" size="sm" color="neutral" variant="ghost" :disabled="queue.busy" @click="queue.setAnswer(row.id)" /></div>
        </details>
      </li>
    </ol>
  </div>
</template>
<style scoped>
.import-queue,.batch-defaults,.queue-row,.queue-summary{display:grid;gap:12px}.batch-defaults,.queue-row{padding:16px;border:1px solid var(--ui-border);border-radius:10px}.batch-defaults{background:var(--ui-bg-muted)}.import-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.queue-rows{display:grid;gap:12px;list-style:none;margin:0;padding:0}.queue-row-heading{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}.queue-row-heading strong{flex:1;overflow-wrap:anywhere}.queue-summary{position:sticky;top:0;background:var(--ui-bg);z-index:1;padding:12px 0;border-bottom:1px solid var(--ui-border)}progress{width:100%;height:6px;accent-color:var(--ui-primary)}.answer-section{font-size:13px}.answer-section summary{cursor:pointer;overflow-wrap:anywhere}.answer-section[open]{display:grid;gap:10px}@media(max-width:720px){.import-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.import-grid{grid-template-columns:1fr}}
</style>
