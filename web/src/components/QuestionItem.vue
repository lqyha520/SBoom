<script setup lang="ts">
import { computed } from 'vue'
import type { Question, SecLayout } from '../types'
import { answerOf, cirNum, escHtml, isBlankVal, spaceOps, stripOptPrefix, tfStem } from '../utils'
import { sanitizeRich } from '../sanitize'

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
/** 应用题：题干下方自动留解答空间（可用大题排版 answerLines 调行数，默认 3 行） */
const isWordProblem = computed(() => props.q.type === 'word_problem')
const answerLines = computed(() => (props.layout as any).answerLines ?? 3)
/** 应用题题干缺问句提醒（LLM 偶发漏问句；只提醒不强改） */
const stemNoQuestion = computed(() => {
  if (!isWordProblem.value) return false
  const s = props.q.stem || ''
  return s.trim() !== '' && !/[？?]\s*$/.test(s.trim())
})

// 算式类题干（口算/竖式/脱式…）的运算符补空格；含汉字的题干原样返回
const stemText = computed(() => spaceOps(isTf.value ? tfStem(props.q.stem || '') : props.q.stem || ''))
const noTag = computed(() => (props.layout.showNo === false ? '' : cirNum(props.no) + ' '))
const lvTag = computed(() => (props.q.difficulty_level ? `[第${props.q.difficulty_level}关] ` : ''))
const fs = computed(() => (props.layout.fontSize ? { fontSize: props.layout.fontSize } : {}))

/* ── 富文本渲染：有编辑缓存用缓存（渲染前净化，防模板里夹带恶意 HTML），否则转义纯文本 ── */
const stemHtml = computed(() =>
  props.q._stemHtml ? sanitizeRich(props.q._stemHtml) : escHtml(lvTag.value + stemText.value),
)
function optHtml(j: number): string {
  const cached = props.q._optsHtml?.[j]
  if (cached != null) return sanitizeRich(cached)
  return `${String.fromCharCode(65 + j)}. ${escHtml(spaceOps(stripOptPrefix(props.q.options?.[j] ?? '')))}`
}

/* ── 编辑回写（同时捕获富文本 HTML 和纯文本） ── */
function stripPrefix(text: string, re: RegExp): string {
  const m = text.trim().match(re)
  return (m ? m[1] : text).trim()
}
function onStemBlur(e: FocusEvent) {
  if (!props.editable) return
  const el = e.target as HTMLElement
  // 写入前净化：剥离粘贴富文本里的事件/脚本，只保留排版标签
  props.q._stemHtml = sanitizeRich(el.innerHTML.replace(/^[①-㊿]\s*/, ''))
  props.q.stem = stripPrefix(stripPrefix(el.innerText, /^[①-㊿]\s*/), /^\[第\d+关\]\s*/)
}
function onOptBlur(e: FocusEvent, j: number) {
  if (!props.editable || !props.q.options) return
  const el = e.target as HTMLElement
  if (!props.q._optsHtml) props.q._optsHtml = []
  props.q._optsHtml[j] = sanitizeRich(el.innerHTML.replace(/^[A-H][.、：:．]\s*/, ''))
  props.q.options[j] = stripPrefix(el.innerText, /^[A-H][.、：:．]\s*/)
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
        <span class="compare-expr" :contenteditable="editable" @blur="onExprBlur($event, 'left_expr')" @keydown.stop>{{ spaceOps(q.left_expr) }}</span>
        <span class="compare-circle"></span>
        <span class="compare-expr" :contenteditable="editable" @blur="onExprBlur($event, 'right_expr')" @keydown.stop>{{ spaceOps(q.right_expr) }}</span>
      </div>
    </template>

    <!-- 常规题 -->
    <template v-else>
      <div data-e="stem" :contenteditable="editable" spellcheck="false" @blur="onStemBlur($event)" v-html="noTag + stemHtml"></div>
      <!-- 应用题缺问句提醒（编辑态可见，打印/导出不含） -->
      <div v-if="stemNoQuestion && editable" class="wp-warn no-print">⚠ 题干缺问句（末尾应有"…多少…？"），请补全后使用</div>
      <!-- 应用题解答留白：默认 3 行，随大题排版 answerLines 配置 -->
      <div v-if="isWordProblem && !showAnswers" class="wp-answer-space" :style="{ height: `${answerLines * 8}mm` }"></div>
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
          v-html="optHtml(j)"
        ></div>
      </div>
      <table v-else-if="q.left_items" class="match-table" data-e="match">
        <tr><th style="width:50%">左栏</th><th style="width:50%">右栏</th></tr>
        <tr v-for="(_, i) in q.left_items" :key="i">
          <td :contenteditable="editable" @blur="onMatchBlur($event, 'left', i)">{{ `（${i + 1}）` }}{{ spaceOps(q.left_items![i]) }}</td>
          <td :contenteditable="editable" @blur="onMatchBlur($event, 'right', i)">{{ `（${i + 1}）` }}{{ spaceOps(q.right_items?.[i]) }}</td>
        </tr>
      </table>
    </template>

    <!-- 行内答案 -->
    <div v-if="showAnswers" class="q-ans-inline">✎ 答案：{{ answerOf(q) }}</div>
  </div>
</template>

<style scoped>
.wp-answer-space {
  /* 解答留白：不设边框，纯空白区域供学生列式作答 */
  margin-top: 1mm;
  flex: none;
}
.wp-warn {
  font-size: 10px;
  color: #d0342c;
  background: #fdecec;
  border-radius: 3px;
  padding: 1px 6px;
  margin-top: 1mm;
  display: inline-block;
}
</style>
