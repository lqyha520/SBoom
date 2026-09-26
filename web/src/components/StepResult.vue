<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import PaperView from './PaperView.vue'
import FormatBar from './FormatBar.vue'
import ZoomControl from './ZoomControl.vue'
import RecoveryActions from './RecoveryActions.vue'
import GenerationTasks from './GenerationTasks.vue'
import QuestionManager from './QuestionManager.vue'
import * as exporter from '../exporter'
import { useFitZoom } from '../useFitZoom'

const store = useExamStore()
const emit = defineEmits<{ library: [] }>()
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
const qualityWarnings = computed(() => paper.value?.sections.flatMap((section, index) => section.warn ? ['第 ' + (index + 1) + ' 大题：' + section.warn] : []) || [])
const exporting = ref('')
const busy = computed(() => !!exporting.value || archiving.value)
const exportError = ref('')
watch(() => store.papers, () => { selected.value = 0; store.layoutMode = false })
function onTitleEdited(title: string, html: string) {
  store.title = title
  store.titleHtml = html
  store.papers.forEach(p => { p.title = title; p.titleHtml = html })
}
async function run(label: string, job: () => Promise<void>) {
  if (busy.value) return
  exportError.value = ''
  exporting.value = label
  try { await job() }
  catch (e: unknown) { exportError.value = '导出失败：' + (e instanceof Error ? e.message : String(e)) }
  finally { exporting.value = '' }
}
function exportPdf(mode: 'student' | 'withAnswers' | 'answersOnly') {
  if (paper.value) run('正在导出 PDF', () => exporter.exportPDF(paper.value!, store.template, store.style, mode))
}
function exportPng() {
  if (paper.value) run('正在导出 PNG', () => exporter.exportPNG(paper.value!, store.template, store.style))
}
function exportBatch(mergeOnly: boolean) {
  run(mergeOnly ? '正在合并 PDF' : '正在打包 ZIP', () => exporter.exportBatch(store.papers, store.template, store.style,
    { addDay: store.addDayLabel, mergeOnly }, message => { exporting.value = message }))
}
function printPaper() { if (stackEl.value) run('正在准备打印', async () => exporter.printStack(stackEl.value!)) }
const pdfMenu = [
  { label: '学生卷 PDF', icon: 'i-lucide-file-text', onSelect: () => exportPdf('student') },
  { label: '试卷与答案 PDF', icon: 'i-lucide-files', onSelect: () => exportPdf('withAnswers') },
  { label: '仅答案 PDF', icon: 'i-lucide-file-check', onSelect: () => exportPdf('answersOnly') },
]
const moreExports = computed(() => [
  [{ label: '下载 PNG', icon: 'i-lucide-image', onSelect: exportPng }, { label: '打印试卷', icon: 'i-lucide-printer', onSelect: printPaper }],
  ...(store.papers.length > 1 ? [[
    { label: '全部试卷 ZIP', icon: 'i-lucide-file-archive', onSelect: () => exportBatch(false) },
    { label: '合并全部 PDF', icon: 'i-lucide-files', onSelect: () => exportBatch(true) },
  ]] : []),
])
function toggleLayout() {
  if (!store.layoutMode) store.recordEdit()
  if (store.layoutMode) paperViewEl.value?.applyLayout()
  else store.showAnswers = false
  store.layoutMode = !store.layoutMode
}
function cancelLayout() { store.layoutMode = false; paperViewEl.value?.repaginate() }
</script>

<template>
  <section v-if="paper" class="result-view" aria-label="生成的试卷">
    <GenerationTasks />
    <QuestionManager v-if="manageQuestions" :paper-index="selected" @close="manageQuestions = false" />
    <div v-if="store.generateWarn || store.generateError || exportError" class="result-notice no-print">
      <UAlert v-if="store.generateWarn" color="warning" variant="soft" :title="store.generateWarn" />
      <RecoveryActions />
      <UAlert v-if="store.generateError || exportError" color="error" variant="soft" :title="exportError || store.generateError" role="alert" />
    </div>
    <div v-if="qualityWarnings.length" class="result-quality no-print"><UAlert color="warning" variant="soft" title="当前试卷待核对" :description="qualityWarnings.join('；')" /></div>
    <div class="result-toolbar no-print">
      <UTooltip text="返回搭建"><UButton icon="i-lucide-arrow-left" color="neutral" variant="ghost" aria-label="返回搭建" :disabled="busy" @click="store.backToBuild()" /></UTooltip>
      <USelect v-model="selected" :items="paperOptions" aria-label="选择试卷" class="paper-picker" :disabled="store.layoutMode || busy || store.generating" />
      <span class="text-xs text-muted">共 {{ store.papers.length }} 份</span>
      <div class="flex-1"></div>
      <UButton label="管理题目" icon="i-lucide-list-checks" variant="outline" :disabled="busy || store.layoutMode || store.generating" @click="manageQuestions = true" />
      <UButton icon="i-lucide-refresh-cw" label="重新生成" color="neutral" variant="outline" :loading="store.generating" :disabled="busy || store.layoutMode" @click="store.regenerate()" />
      <UButton icon="i-lucide-cloud-upload" label="保存到云端" color="neutral" variant="outline" :loading="archiving" :disabled="busy || store.layoutMode || store.generating || store.accountChanged" @click="showCloudSave = true" />
      <UButtonGroup>
        <UButton icon="i-lucide-download" label="下载 PDF" :loading="!!exporting" :disabled="busy || store.layoutMode || store.generating" @click="exportPdf('student')" />
        <UDropdownMenu :items="pdfMenu"><UButton icon="i-lucide-chevron-down" aria-label="PDF 导出选项" :disabled="busy || store.layoutMode || store.generating" /></UDropdownMenu>
      </UButtonGroup>
      <UDropdownMenu :items="moreExports"><UButton icon="i-lucide-ellipsis" color="neutral" variant="outline" aria-label="更多导出方式" :disabled="busy || store.layoutMode || store.generating" /></UDropdownMenu>
    </div>
    <div class="preview-toolbar result-editbar no-print">
      <div class="actions-row"><FormatBar /><div class="toolbar-divider"></div><USwitch v-model="store.showAnswers" label="显示答案" size="sm" :disabled="store.layoutMode || busy" /></div>
      <div class="actions-row">
        <template v-if="!store.layoutMode"><UButton icon="i-lucide-move" label="排版模式" color="neutral" variant="ghost" size="xs" :disabled="busy" @click="toggleLayout" /></template>
        <template v-else><UButton label="取消" color="neutral" variant="ghost" size="xs" @click="cancelLayout" /><UButton icon="i-lucide-check" label="完成排版" size="xs" @click="toggleLayout" /></template>
      </div>
    </div>
    <div v-if="exporting" class="px-5 py-2 text-xs text-primary bg-default no-print" role="status">{{ exporting }}</div>
    <div ref="stackEl" class="preview-scroll">
      <PaperView :key="selected" ref="paperViewEl" :paper="paper" :template="store.template" :style="store.style" :show-answers="store.showAnswers" :editable="!busy" :layout-mode="store.layoutMode" :add-day="store.addDayLabel" :zoom="zoom"
        @title-edited="onTitleEdited" @toggle-element="store.toggleHiddenElement($event)" @title-offset="value => store.setStyle({ titleOffsetY: value })" />
    </div>
    <div class="preview-footer no-print"><span>A4 <span class="mx-1 text-dimmed">/</span> {{ questionCount }} 道题目</span><ZoomControl :zoom="zoom" :manual="manual" @change="setManual" /></div>
    <CloudSaveDialog v-if="showCloudSave" :open="showCloudSave" :selected="selected" @close="showCloudSave = false" @busy="archiving = $event" @library="showCloudSave = false; emit('library')" />
  </section>
</template>
