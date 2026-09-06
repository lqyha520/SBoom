<script setup lang="ts">
import { computed } from 'vue'
import type { Question, SecLayout } from '../types'
import { answerOf, cirNum, isBlankVal, stripOptPrefix, tfStem } from '../utils'

const props = defineProps<{
  q: Question
  /** 题号（节内 1 起） */
  no: number
  layout: SecLayout
  showAnswers: boolean
  editable: boolean
}>()

const emit = defineEmits<{
  (e: 'delete'): void
}>()

const isSplit = computed(() => props.q.top != null)
const isCompare = computed(() => props.q.left_expr != null)
const isTf = computed(() => props.q.type === 'true_false')

const stemText = computed(() => (isTf.value ? tfStem(props.q.stem || '') : props.q.stem || ''))
const noTag = computed(() => (props.layout.showNo === false ? '' : cirNum(props.no) + ' '))
const lvTag = computed(() => (props.q.difficulty_level ? `[第${props.q.difficulty_level}关] ` : ''))
const fs = computed(() => (props.layout.fontSize ? { fontSize: props.layout.fontSize } : {}))

/* ── 编辑回写 ── */
function stripPrefix(text: string, re: RegExp): string {
  const m = text.trim().match(re)
  return (m ? m[1] : text).trim()
}
function onStemBlur(e: FocusEvent) {
  if (!props.editable) return
  const t = (e.target as HTMLElement).innerText
  props.q.stem = stripPrefix(stripPrefix(t, /^[①-⑳]\s*/), /^\[第\d+关\]\s*/)
}
function onOptBlur(e: FocusEvent, j: number) {
  if (!props.editable || !props.q.options) return
  const t = (e.target as HTMLElement).innerText
  props.q.options[j] = stripPrefix(t, /^[A-H][.、：:．]\s*/)
}
function onMatchBlur(e: FocusEvent, side: 'left' | 'right', i: number) {
  if (!props.editable) return
  const t = (e.target as HTMLElement).innerText
  const v = stripPrefix(t, /^（\d+）\s*/)
  if (side === 'left' && props.q.left_items) props.q.left_items[i] = v || ' '
  if (side === 'right' && props.q.right_items) props.q.right_items[i] = v || ' '
}
function onSplitBlur(e: FocusEvent, field: 'top' | 'left' | 'right') {
  if (!props.editable) return
  const t = (e.target as HTMLElement).innerText.trim()
  if (t !== '' || isBlankVal((props.q as any)[field])) (props.q as any)[field] = t
}
function onExprBlur(e: FocusEvent, field: 'left_expr' | 'right_expr') {
  if (!props.editable) return
  ;(props.q as any)[field] = (e.target as HTMLElement).innerText.trim()
}
</script>

<template>
  <div class="q can-edit" :data-qid="q._qid" :style="fs">
    <!-- 数的分成 -->
    <template v-if="isSplit">
      <span v-if="layout.showNo !== false">{{ noTag }}</span>
      <div class="split-wrap">
        <div
          class="split-box" :class="{ blank: isBlankVal(q.top) }" :contenteditable="editable"
          @blur="onSplitBlur($event, 'top')" @keydown.stop
        >{{ isBlankVal(q.top) ? '' : q.top }}</div>
        <svg class="split-lines" viewBox="0 0 120 22" preserveAspectRatio="none"><path d="M60 0 L30 22 M60 0 L90 22" /></svg>
        <div class="split-bottom">
          <span class="split-box" :class="{ blank: isBlankVal(q.left) }" :contenteditable="editable" @blur="onSplitBlur($event, 'left')" @keydown.stop>{{ isBlankVal(q.left) ? '' : q.left }}</span>
          <span class="split-box" :class="{ blank: isBlankVal(q.right) }" :contenteditable="editable" @blur="onSplitBlur($event, 'right')" @keydown.stop>{{ isBlankVal(q.right) ? '' : q.right }}</span>
        </div>
      </div>
    </template>

    <!-- 比大小 -->
    <template v-else-if="isCompare">
      <span v-if="layout.showNo !== false">{{ noTag }}</span>
      <div class="compare-row">
        <span class="compare-expr" :contenteditable="editable" @blur="onExprBlur($event, 'left_expr')" @keydown.stop>{{ q.left_expr }}</span>
        <span class="compare-circle"></span>
        <span class="compare-expr" :contenteditable="editable" @blur="onExprBlur($event, 'right_expr')" @keydown.stop>{{ q.right_expr }}</span>
      </div>
    </template>

    <!-- 常规题 -->
    <template v-else>
      <div data-e="stem" :contenteditable="editable" spellcheck="false" @blur="onStemBlur($event)">{{ noTag }}{{ lvTag }}{{ stemText }}</div>
      <div
        v-if="q.options"
        class="opts"
        data-e="opts"
        :style="{ gridTemplateColumns: `repeat(${layout.optCols}, 1fr)` }"
      >
        <div
          v-for="(o, j) in q.options"
          :key="j"
          :contenteditable="editable"
          spellcheck="false"
          @blur="onOptBlur($event, j)"
        >{{ String.fromCharCode(65 + j) }}. {{ stripOptPrefix(o) }}</div>
      </div>
      <table v-else-if="q.left_items" class="match-table" data-e="match">
        <tr><th style="width:50%">左栏</th><th style="width:50%">右栏</th></tr>
        <tr v-for="(_, i) in q.left_items" :key="i">
          <td :contenteditable="editable" @blur="onMatchBlur($event, 'left', i)">{{ `（${i + 1}）` }}{{ q.left_items![i] }}</td>
          <td :contenteditable="editable" @blur="onMatchBlur($event, 'right', i)">{{ `（${i + 1}）` }}{{ q.right_items?.[i] }}</td>
        </tr>
      </table>
    </template>

    <!-- 行内答案 -->
    <div v-if="showAnswers" class="q-ans-inline">✎ 答案：{{ answerOf(q) }}</div>
  </div>
</template>
