<script setup lang="ts">
import { computed } from 'vue'
import type { Question, SecLayout } from '../types'
import { answerOf, cirNum, escHtml, isBlankVal, spaceOps, stripOptPrefix, tfStem } from '../utils'
import { sanitizeRich } from '../sanitize'
import { labelPattern, optionLabel, readEdited, startsWithLabel } from '../rich-edit'

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
/** 选项 = 字母 + 内容；编辑缓存只存内容（早期缓存可能已带字母，此时不再重复加） */
function optHtml(j: number): string {
  const cached = props.q._optsHtml?.[j]
  if (cached != null && startsWithLabel(cached, optionLabel(j))) return sanitizeRich(cached)
  const body = cached != null ? sanitizeRich(cached) : escHtml(spaceOps(stripOptPrefix(props.q.options?.[j] ?? '')))
  return `${String.fromCharCode(65 + j)}. ${body}`
}

/* ── 编辑回写（同时捕获富文本 HTML 和纯文本）──
   题号、选项字母、连线序号是渲染时加在最前面的标签，回写时按渲染的原样去掉（见 rich-edit.ts）。
   只是点进去又离开、内容没变时不写回，免得把渲染用的格式（运算符空格、判断题括号）写进数据。 */
function onStemBlur(e: FocusEvent) {
  if (!props.editable) return
  const label = props.layout.showNo === false ? null : labelPattern(cirNum(props.no))
  // 写入前净化：剥离粘贴富文本里的事件/脚本，只保留排版标签
  const edited = readEdited(e.target as HTMLElement, label)
  if (edited.html === readEdited(noTag.value + stemHtml.value, label).html) return
  props.q._stemHtml = edited.html
  props.q.stem = edited.text.replace(/^\[第\d+关\]\s*/, '')
}
function onOptBlur(e: FocusEvent, j: number) {
  if (!props.editable || !props.q.options) return
  const label = optionLabel(j)
  const edited = readEdited(e.target as HTMLElement, label)
  if (edited.html === readEdited(optHtml(j), label).html) return
  if (!props.q._optsHtml) props.q._optsHtml = []
  props.q._optsHtml[j] = edited.html
  props.q.options[j] = edited.text
}
function onMatchBlur(e: FocusEvent, side: 'left' | 'right', i: number) {
  if (!props.editable) return
  const items = side === 'left' ? props.q.left_items : props.q.right_items
  if (!items) return
  const text = readEdited(e.target as HTMLElement, labelPattern(`（${i + 1}）`)).text
  if (text === spaceOps(items[i] ?? '').trim()) return
  items[i] = text || ' '
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
        <thead><tr><th style="width:50%">左栏</th><th style="width:50%">右栏</th></tr></thead>
        <tbody>
          <tr v-for="(_, i) in q.left_items" :key="i">
            <td :contenteditable="editable" @blur="onMatchBlur($event, 'left', i)">{{ `（${i + 1}）` }}{{ spaceOps(q.left_items![i]) }}</td>
            <td :contenteditable="editable" @blur="onMatchBlur($event, 'right', i)">{{ `（${i + 1}）` }}{{ spaceOps(q.right_items?.[i]) }}</td>
          </tr>
        </tbody>
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
