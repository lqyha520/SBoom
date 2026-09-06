<script setup lang="ts">
import { computed } from 'vue'
import type { PaperSection, Question } from '../types'
import { ENCOURAGE_MAP, TYPE_NAME } from '../constants'
import { secTitle } from '../utils'
import QuestionItem from './QuestionItem.vue'

const props = defineProps<{
  section: PaperSection
  /** 全卷中的大题序号（0 起，用于 一、二、三 标题） */
  secIndex: number
  /** 全卷起始题号（题号跨大题连续） */
  startNo: number
  showScore: boolean
  showAnswers: boolean
  editable: boolean
  encourage: boolean
  scores?: Map<Question, number>
}>()

const layout = computed(() => props.section.layout)
const qs = computed(() => props.section.data.questions || [])
const useTable = computed(() => layout.value.tableBorder !== 'none')
const tblColor = computed(() => (layout.value.tableBorder === 'dashed' ? '#ccc' : '#333'))
const enc = computed(() => (props.encourage ? ENCOURAGE_MAP[props.section.type] || '' : ''))
const title = computed(() => secTitle(props.section.type, props.secIndex))

const secScore = computed(() => {
  if (!props.scores) return 0
  return qs.value.reduce((s, q) => s + (props.scores!.get(q) || 0), 0)
})

const rows = computed(() => {
  const cols = layout.value.qCols
  const out: Question[][] = []
  for (let i = 0; i < qs.value.length; i += cols) out.push(qs.value.slice(i, i + cols))
  return out
})
const fs = computed(() => (layout.value.fontSize ? { fontSize: layout.value.fontSize } : {}))
const gridStyle = computed(() => ({
  display: 'grid',
  gridTemplateColumns: `repeat(${layout.value.qCols}, 1fr)`,
  columnGap: layout.value.qCols > 1 ? '12mm' : '0',
}))
</script>

<template>
  <div class="sec-block" :data-type="section.type" :data-sid="section._sid || section.type + '_' + secIndex">
    <h2 class="sec">
      <span>{{ title }}</span>
      <span v-if="enc" class="encourage">{{ enc }}</span>
      <span v-if="showScore && scores" class="score-box">共 {{ secScore }} 分</span>    </h2>

    <div v-if="section.type === 'reading' && section.data.passage" class="reading-box" data-e="passage">{{ section.data.passage }}</div>

    <!-- 表格模式 -->
    <table v-if="useTable" class="q-table" :style="{ border: `1px ${layout.tableBorder} ${tblColor}` }">
      <tr v-for="(row, ri) in rows" :key="ri">
        <td
          v-for="(q, ci) in row"
          :key="q._qid || ci"
          :style="{ border: `1px ${layout.tableBorder} ${tblColor}`, padding: '1mm 3mm', verticalAlign: 'top', ...(fs as any) }"
        >
          <QuestionItem :q="q" :no="startNo + ri * layout.qCols + ci" :layout="layout" :show-answers="showAnswers" :editable="editable" />
        </td>
        <td
          v-for="k in layout.qCols - row.length"
          :key="'pad' + k"
          :style="{ border: `1px ${layout.tableBorder} ${tblColor}`, padding: '1mm 3mm' }"
        ></td>
      </tr>
    </table>

    <!-- 网格模式 -->
    <div v-else class="q-grid" :style="gridStyle as any">
      <QuestionItem
        v-for="(q, i) in qs"
        :key="q._qid || i"
        :q="q"
        :no="startNo + i"
        :layout="layout"
        :show-answers="showAnswers"
        :editable="editable"
      />
    </div>
  </div>
</template>

<style scoped>
.sec-block { display: flow-root; position: relative; }
</style>
