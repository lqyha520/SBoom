<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import PaperView from './PaperView.vue'
import PaperEditToolbar from './PaperEditToolbar.vue'
import ZoomControl from './ZoomControl.vue'
import RecoveryActions from './RecoveryActions.vue'
import GenerationTasks from './GenerationTasks.vue'
import QuestionManager from './QuestionManager.vue'
import * as exporter from '../exporter'
import { deepClone } from '../utils'
import { useFitZoom } from '../useFitZoom'

const store = useExamStore()
const emit = defineEmits<{ library: []; 'open-settings': [] }>()
const CloudSaveDialog = defineAsyncComponent(() => import('./CloudSaveDialog.vue'))
const showCloudSave = ref(false)
const manageQuestions = ref(false)
const archiving = ref(false)
const stackEl = ref<HTMLElement | null>(null)
const paperViewEl = ref<InstanceType<typeof PaperView> | null>(null)
const { zoom, manual, setManual } = useFitZoom(stackEl)
const selected = ref(0)
const paper = computed(() => store.papers[selected.value] || store.papers[0])
const paperOptions = computed(() => store.papers.map((p, index) => ({ label: '第 ' + (p.day || index + 1) + ' 份试卷', value: index })))
const questionCount = computed(() => paper.value?.sections.reduce((total, section) => total + section.data.questions.length, 0) || 0)
const qualityWarnings = computed(() => paper.value?.sections.flatMap((section, index) => section.warn ? [{ index, message: section.warn }] : []) || [])
const qualityOpen = ref(false)
const warningSummary = computed(() => [
  store.failedCount ? store.failedCount + ' 份试卷尚未完成' : '',
  qualityWarnings.value.length ? qualityWarnings.value.length + ' 个大题待核对' : '',
].filter(Boolean).join(' · ') || store.generateWarn)
const exporting = ref('')
const exportNotice = ref('')
const editingOpen = ref(false)
const titleScope = ref('current')
const titleScopes = [{ label: '仅当前试卷', value: 'current' }, { label: '全部试卷', value: 'all' }]
let exportController: AbortController | undefined
function leave() { exportController?.abort(); if (store.layoutMode) store.finishLayout(true) }
onBeforeUnmount(leave)
onDeactivated(leave)
const busy = computed(() => !!exporting.value || archiving.value)
const exportError = ref('')
watch(() => store.papers, () => { selected.value = 0 })
function onTitleEdited(title: string, html: string) {
  if (titleScope.value === 'all') {
    store.title = title
    store.titleHtml = html
    store.papers.forEach(p => { p.title = title; p.titleHtml = html })
  } else if (paper.value) {
    paper.value.title = title
    paper.value.titleHtml = html
  }
}
async function run(label: string, job: (signal: AbortSignal) => Promise<void>) {
  if (busy.value) return
  exportError.value = ''
  exportNotice.value = ''
  exporting.value = label
  exportController = new AbortController()
  try { await job(exportController.signal); exportNotice.value = '导出完成' }
  catch (e: unknown) { exportError.value = e instanceof DOMException && e.name === 'AbortError' ? '导出已取消' : '导出失败：' + (e instanceof Error ? e.message : String(e)) }
  finally { exporting.value = ''; exportController = undefined }
}
function exportPdf(mode: 'student' | 'withAnswers' | 'answersOnly') {
  if (paper.value) { const data = deepClone(paper.value), template = deepClone(store.template), style = deepClone(store.style); run('正在导出 PDF', signal => exporter.exportPDF(data, template, style, mode, signal, message => { exporting.value = message })) }
}
function exportPng() {
  if (paper.value) { const data = deepClone(paper.value), template = deepClone(store.template), style = deepClone(store.style); run('正在导出 PNG', signal => exporter.exportPNG(data, template, style, signal)) }
}
function exportBatch(mergeOnly: boolean) {
  const papers = deepClone(store.papers), template = deepClone(store.template), style = deepClone(store.style), addDay = store.addDayLabel
  run(mergeOnly ? '正在合并 PDF' : '正在打包 ZIP', signal => exporter.exportBatch(papers, template, style,
    { addDay, mergeOnly, signal }, message => { exporting.value = message }))
}
function printPaper() { if (stackEl.value) run('正在准备打印', async () => exporter.printStack(stackEl.value!)) }
const pdfMenu = [
  { label: '学生卷 PDF', icon: 'i-lucide-file-text', onSelect: () => exportPdf('student') },
  { label: '试卷与答案 PDF', icon: 'i-lucide-files', onSelect: () => exportPdf('withAnswers') },
  { label: '仅答案 PDF', icon: 'i-lucide-file-check', onSelect: () => exportPdf('answersOnly') },
]
const moreExports = computed(() => [
  [{ label: '重新生成', icon: 'i-lucide-refresh-cw', disabled: busy.value || store.generating || store.layoutMode, onSelect: confirmRegenerate },
    { label: '保存到云端', icon: 'i-lucide-cloud-upload', disabled: busy.value || store.generating || store.layoutMode || store.accountChanged, onSelect: () => { showCloudSave.value = true } }],
  [{ label: '下载 PNG', icon: 'i-lucide-image', onSelect: exportPng }, { label: '打印试卷', icon: 'i-lucide-printer', onSelect: printPaper }],
  ...(store.papers.length > 1 ? [[
    { label: '全部试卷 ZIP', icon: 'i-lucide-file-archive', onSelect: () => exportBatch(false) },
    { label: '合并全部 PDF', icon: 'i-lucide-files', onSelect: () => exportBatch(true) },
  ]] : []),
])
function toggleLayout() {
  if (store.layoutMode) { paperViewEl.value?.applyLayout(); store.finishLayout() }
  else { store.beginLayout(); store.showAnswers = false }
}
async function confirmRegenerate() {
  await store.requestGeneration()
}
function cancelLayout() { store.finishLayout(true); paperViewEl.value?.repaginate() }
</script>

<template>
  <section class="result-view" aria-label="生成的试卷">
    <p v-if="exportNotice" class="px-4 py-2 text-sm text-primary bg-default" role="status">{{ exportNotice }}</p>
    <GenerationTasks />
    <QuestionManager v-if="paper && manageQuestions" :paper-index="selected" @close="manageQuestions = false" />
    <div v-if="warningSummary || store.generateError || exportError" class="result-notice no-print">
      <div v-if="warningSummary" class="quality-summary" role="status"><UIcon name="i-lucide-triangle-alert" class="size-4" /><span>{{ warningSummary }}</span><UButton v-if="qualityWarnings.length" :label="qualityOpen ? '收起' : '查看详情'" :icon="qualityOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" color="warning" variant="ghost" size="sm" :aria-expanded="qualityOpen" @click="qualityOpen = !qualityOpen" /></div>
      <UCollapsible v-if="warningSummary" v-model:open="qualityOpen">
        <template #content><ul class="quality-details"><li v-for="warning in qualityWarnings" :key="warning.index"><strong>第 {{ warning.index + 1 }} 大题</strong><p>{{ warning.message }}</p></li></ul><div class="actions-row pb-2"><UButton label="核对题目" icon="i-lucide-list-checks" variant="outline" size="sm" :disabled="busy || store.generating || store.layoutMode" @click="manageQuestions = true" /><UButton label="调整出题条件" icon="i-lucide-arrow-left" variant="ghost" size="sm" :disabled="busy || store.layoutMode" @click="store.backToBuild()" /></div></template>
      </UCollapsible>
      <RecoveryActions />
      <UAlert v-if="store.generateError || exportError" color="error" variant="soft" :title="exportError || store.generateError" role="alert" />
    </div>
    <div v-if="!paper" class="p-8" role="status">
      <p>{{ store.generating ? (store.generateProgress || '正在生成试卷…') : '暂时没有可用试卷，请查看任务状态或修改条件。' }}</p>
      <RecoveryActions />
      <UButton label="返回搭建" variant="outline" @click="store.backToBuild()" />
    </div>
    <template v-if="paper">
    <div class="result-toolbar no-print">
      <UTooltip text="返回搭建"><UButton icon="i-lucide-arrow-left" color="neutral" variant="ghost" aria-label="返回搭建" :disabled="busy || store.layoutMode" @click="store.backToBuild()" /></UTooltip>
      <USelect v-model="selected" :items="paperOptions" aria-label="选择试卷" class="paper-picker" :disabled="store.layoutMode || busy || store.generating" />
      <span class="result-count text-xs text-muted">共 {{ store.papers.length }} 份</span>
      <div class="flex-1"></div>
      <UButton class="result-secondary" icon="i-lucide-refresh-cw" label="重新生成" color="neutral" variant="outline" :loading="store.generating" :disabled="busy || store.layoutMode" @click="confirmRegenerate" />
      <UButton class="result-secondary" icon="i-lucide-cloud-upload" label="保存到云端" color="neutral" variant="outline" :loading="archiving" :disabled="busy || store.layoutMode || store.generating || store.accountChanged" @click="showCloudSave = true" />
      <UButton class="result-edit-toggle" icon="i-lucide-sliders-horizontal" aria-label="卷面编辑工具" :aria-expanded="editingOpen" variant="outline" color="neutral" @click="editingOpen = !editingOpen" />
      <UButtonGroup>
        <UButton icon="i-lucide-download" label="下载学生卷" :loading="!!exporting" :disabled="busy || store.layoutMode || store.generating" @click="exportPdf('student')" />
        <UDropdownMenu :items="pdfMenu"><UButton icon="i-lucide-chevron-down" aria-label="PDF 导出选项" :disabled="busy || store.layoutMode || store.generating" /></UDropdownMenu>
      </UButtonGroup>
      <UDropdownMenu :items="moreExports"><UButton icon="i-lucide-ellipsis" color="neutral" variant="outline" aria-label="更多导出方式" :disabled="busy || store.layoutMode || store.generating" /></UDropdownMenu>
    </div>
    <PaperEditToolbar v-model:answers="store.showAnswers" class="result-editbar" :class="{ 'editing-open': editingOpen || store.layoutMode }" :layout-mode="store.layoutMode" :disabled="busy || store.generating" :can-layout="!!paper.sections.length" manage @settings="emit('open-settings')" @manage="manageQuestions = true" @layout="toggleLayout" @cancel="cancelLayout" />
    <div class="result-scope no-print">
      <label for="title-scope">标题修改范围</label>
      <USelect id="title-scope" v-model="titleScope" :items="titleScopes" size="sm" :disabled="busy || store.generating || store.layoutMode" />
      <span>卷面样式应用全部试卷</span>
      <span v-if="store.showAnswers">预览已显示答案；含答案文件请在 PDF 导出选项中选择</span>
    </div>
    <div v-if="exporting" class="px-5 py-2 text-xs text-primary bg-default no-print"><span role="status">{{ exporting }}</span><UButton label="取消导出" variant="ghost" size="xs" @click="exportController?.abort()" /></div>
    <div ref="stackEl" class="preview-scroll">
      <PaperView :key="selected" ref="paperViewEl" :paper="paper" :template="store.template" :style="store.style" :show-answers="store.showAnswers" :editable="!busy" :layout-mode="store.layoutMode" :add-day="store.addDayLabel" :zoom="zoom"
        @title-edited="onTitleEdited" @toggle-element="store.toggleHiddenElement($event)" @title-offset="value => store.setStyle({ titleOffsetY: value })" />
    </div>
    <div class="preview-footer no-print"><span>A4 <span class="mx-1 text-dimmed">/</span> {{ questionCount }} 道题目</span><ZoomControl :zoom="zoom" :manual="manual" @change="setManual" /></div>
    <CloudSaveDialog v-if="showCloudSave" :open="showCloudSave" :selected="selected" @close="showCloudSave = false" @busy="archiving = $event" @library="showCloudSave = false; emit('library')" />
    </template>
  </section>
</template>
