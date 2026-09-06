<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { summaryText } from '../utils'
import PaperView from './PaperView.vue'
import * as exporter from '../exporter'
import { useFitZoom } from '../useFitZoom'

const store = useExamStore()

const stackEl = ref<HTMLElement | null>(null)
const paperViewEl = ref<InstanceType<typeof PaperView> | null>(null)
const { zoom } = useFitZoom(stackEl)

const paper = computed(() => store.papers[0])
const summary = computed(() => (paper.value ? summaryText(paper.value.grade, paper.value.subject, paper.value.keyword, paper.value.sections) : ''))

/* ── 导出状态 ── */
const exporting = ref('')
const exportErr = ref('')

async function run(btnLabel: string, job: () => Promise<void>) {
  if (exporting.value) return
  exportErr.value = ''
  exporting.value = btnLabel
  try {
    await job()
  } catch (e: any) {
    exportErr.value = '导出失败：' + (e?.message || e)
  } finally {
    exporting.value = ''
  }
}

const busy = (label: string) => exporting.value === label

function exportPdf(mode: 'student' | 'withAnswers' | 'answersOnly') {
  if (!paper.value || !stackEl.value) return
  run('pdf', () => exporter.exportPDF(paper.value!, store.template, store.style, stackEl.value!, mode))
}

function exportPng() {
  if (!paper.value || !stackEl.value) return
  run('png', () => exporter.exportPNG(paper.value!, store.template, store.style, stackEl.value!))
}

function exportBatch(mergeOnly: boolean) {
  if (!paper.value || !stackEl.value) return
  run(mergeOnly ? 'merge' : 'zip', () =>
    exporter.exportBatch(store.papers, store.template, store.style, stackEl.value!, {
      addDay: store.addDayLabel,
      mergeOnly,
    }, msg => { exporting.value = msg }),
  )
}

function printPaper() {
  if (!stackEl.value) return
  exporter.printStack(stackEl.value)
}

/* ── 排版模式 ── */
async function toggleLayout() {
  if (store.layoutMode) {
    // 完成：DOM 回写数据
    paperViewEl.value?.applyLayout()
    store.layoutMode = false
  } else {
    store.showAnswers = false
    store.layoutMode = true
  }
}
function cancelLayout() {
  store.layoutMode = false
  paperViewEl.value?.repaginate()
}
</script>

<template>
  <div class="result-view" v-if="paper">
    <!-- 工具栏 -->
    <div class="card no-print" style="flex: none;">
      <div class="result-toolbar" style="margin-bottom: 0;">
        <button class="btn primary" :disabled="!!exporting" @click="exportPdf('student')">
          <template v-if="busy('pdf')"><span class="spin"></span> 导出中…</template>
          <template v-else>下载 PDF</template>
        </button>
        <button class="btn" :disabled="!!exporting" @click="exportPng">下载 PNG</button>
        <button class="btn" :disabled="!!exporting" @click="printPaper">打印</button>
        <span class="sep"></span>
        <button class="btn" @click="store.showAnswers = !store.showAnswers">
          {{ store.showAnswers ? '隐藏答案' : '预览答案' }}
        </button>
        <button class="btn" :disabled="!!exporting" @click="exportPdf('answersOnly')">导出答案 PDF</button>
        <span class="sep"></span>
        <template v-if="!store.layoutMode">
          <button class="btn" @click="toggleLayout">排版模式</button>
        </template>
        <template v-else>
          <span style="font-size: 12px; color: var(--amber);">排版模式：⠿ 拖动排序 · 点击文字编辑 · ✕ 删除 · ⤡ 调整大小</span>
          <button class="btn primary" @click="toggleLayout">✓ 完成排版</button>
          <button class="btn" @click="cancelLayout">取消</button>
        </template>
        <span class="sep"></span>
        <template v-if="store.papers.length > 1">
          <button class="btn" :disabled="!!exporting" @click="exportBatch(false)">
            <template v-if="busy('zip') || busy('正在打包…')"><span class="spin"></span> 处理中…</template>
            <template v-else>导出全部（{{ store.papers.length }} 份 ZIP）</template>
          </button>
          <button class="btn" :disabled="!!exporting" @click="exportBatch(true)">合并 PDF</button>
        </template>
        <button class="btn" :disabled="store.generating" @click="store.regenerate()">
          <template v-if="store.generating"><span class="spin"></span> 生成中…</template>
          <template v-else>再来一批</template>
        </button>
        <span class="sep"></span>
        <span class="result-summary" style="margin-bottom: 0; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" :title="summary">
          {{ summary }}<template v-if="store.papers.length > 1">（{{ store.papers.length }} 份）</template>
        </span>
        <span style="flex: 1;"></span>
        <button class="btn ghost" @click="store.backToBuild()">← 返回调整</button>
      </div>
      <div v-if="exportErr" style="padding: 0 16px 12px; color: var(--red); font-size: 13px;">{{ exportErr }}</div>
    </div>

    <!-- A4 纸 -->
    <div ref="stackEl" class="preview-scroll" style="padding: 16px;">
      <PaperView
        ref="paperViewEl"
        :paper="paper"
        :template="store.template"
        :style="store.style"
        :show-answers="store.showAnswers"
        :editable="true"
        :layout-mode="store.layoutMode"
        :add-day="store.addDayLabel"
        :zoom="zoom"
      />
    </div>
  </div>
</template>
