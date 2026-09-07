<script setup lang="ts">
/**
 * 纸面富文本工具条：加粗 / 字号滑条 / 颜色
 * 字号滑条统一逻辑：
 *   - 选中了纸面文字 → 调整选中文字的字号（1-7 档）
 *   - 没选中 → 调整试卷大标题的字号（60%-200%）
 * 颜色同理：选中文字改文字颜色；未选中改标题颜色。
 * 注意：滑条/色板不 prevent mousedown（否则拖不动），选区用 saved 恢复。
 */
import { computed, ref, onBeforeUnmount, onMounted } from 'vue'
import { useExamStore } from '../stores/exam'

const store = useExamStore()

let saved: Range | null = null

function editableHostOf(node: Node | null): HTMLElement | null {
  let el = node
  while (el) {
    if (el.nodeType === 1) {
      const e = el as HTMLElement
      if (e.getAttribute('contenteditable') === 'true') return e
    }
    el = el.parentNode
  }
  return null
}

function onSelChange() {
  const s = document.getSelection()
  if (s && s.rangeCount > 0) {
    const host = editableHostOf(s.anchorNode)
    if (host && host.closest('.paper')) saved = s.getRangeAt(0).cloneRange()
  }
}
onMounted(() => document.addEventListener('selectionchange', onSelChange))
onBeforeUnmount(() => document.removeEventListener('selectionchange', onSelChange))

const COLORS = [
  '#d0342c', '#e67e22', '#f1c40f', '#27ae60',
  '#2980b9', '#8e44ad', '#16a085', '#34495e',
]

/** 当前是否有纸面选区（决定滑条作用于选中文字还是标题） */
const hasSelection = ref(false)
function refreshHasSelection() {
  const s = document.getSelection()
  hasSelection.value = !!(s && !s.isCollapsed && s.rangeCount && editableHostOf(s.anchorNode)?.closest('.paper'))
}
onMounted(() => document.addEventListener('selectionchange', refreshHasSelection))
onBeforeUnmount(() => document.removeEventListener('selectionchange', refreshHasSelection))

/** 作用于选中文字的字号（1-7 档，execCommand fontSize） */
const sizeVal = ref(3)

function applyFontSize(v: number) {
  sizeVal.value = v
  const s = document.getSelection()
  let host: HTMLElement | null = null
  if (s && s.rangeCount && !s.isCollapsed) host = editableHostOf(s.anchorNode)
  if (!host && saved && s) {
    // 恢复保存的选区
    host = editableHostOf(saved.startContainer)
    if (host) {
      s.removeAllRanges()
      s.addRange(saved)
    }
  }
  if (host && s && !s.isCollapsed) {
    host.focus({ preventScroll: true })
    document.execCommand('fontSize', false, String(v))
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

function applyColor(c: string) {
  const s = document.getSelection()
  let host: HTMLElement | null = null
  if (s && s.rangeCount && !s.isCollapsed) host = editableHostOf(s.anchorNode)
  if (!host && saved && s) {
    host = editableHostOf(saved.startContainer)
    if (host) {
      s.removeAllRanges()
      s.addRange(saved)
    }
  }
  if (host && s && !s.isCollapsed) {
    host.focus({ preventScroll: true })
    document.execCommand('foreColor', false, c)
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

function applyBold() {
  const s = document.getSelection()
  let host: HTMLElement | null = null
  if (s && s.rangeCount && !s.isCollapsed) host = editableHostOf(s.anchorNode)
  if (!host && saved && s) {
    host = editableHostOf(saved.startContainer)
    if (host) {
      s.removeAllRanges()
      s.addRange(saved)
    }
  }
  if (host && s && !s.isCollapsed) {
    host.focus({ preventScroll: true })
    document.execCommand('bold', false, undefined)
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

const SIZE_NAMES = ['', '很小', '小', '标准', '大', '更大', '特大', '最大']
const targetHint = computed(() => (hasSelection.value ? '选中文字' : '标题'))
</script>

<template>
  <span class="fmt-bar">
    <button class="fmt-btn" :title="`加粗（${targetHint}）`" @mousedown.prevent @click="applyBold"><b>B</b></button>
    <span class="fmt-size" :title="`字号：选中文字时改选中文字，否则改${hasSelection ? '选中文字' : '试卷标题'}`">
      <span class="fmt-size-label">{{ targetHint }}</span>
      <input
        v-if="hasSelection"
        type="range" min="1" max="7" step="1"
        :value="sizeVal"
        @input="applyFontSize(parseInt(($event.target as HTMLInputElement).value))"
        class="fmt-size-range"
      >
      <input
        v-else
        type="range" min="60" max="200" step="5"
        :value="Math.round((store.style.titleScale ?? 1) * 100)"
        @input="store.setStyle({ titleScale: parseInt(($event.target as HTMLInputElement).value) / 100 })"
        class="fmt-size-range"
      >
      <span class="fmt-size-val">{{ hasSelection ? (SIZE_NAMES[sizeVal] || sizeVal) : Math.round((store.style.titleScale ?? 1) * 100) + '%' }}</span>
    </span>
    <span class="fmt-colors" :title="`颜色：选中文字时改选中文字，否则为标题准备（先选中标题文字）`">
      <button
        v-for="c in COLORS"
        :key="c"
        class="fmt-swatch"
        :style="{ background: c }"
        :title="c"
        @click="applyColor(c)"
      ></button>
    </span>
  </span>
</template>

<style scoped>
.fmt-bar { display: inline-flex; align-items: center; gap: 6px; }
.fmt-btn {
  border: 1px solid var(--border2);
  background: var(--surface);
  border-radius: 4px;
  font-size: 11px;
  padding: 2px 8px;
  color: var(--ink2);
  cursor: pointer;
  line-height: 1.5;
}
.fmt-btn:hover { border-color: var(--primary); color: var(--primary); }
.fmt-size { display: inline-flex; align-items: center; gap: 4px; padding: 0 4px; }
.fmt-size-label { font-size: 11px; color: var(--primary); white-space: nowrap; }
.fmt-size-range { width: 70px; accent-color: var(--primary); height: 14px; cursor: pointer; }
.fmt-size-val { font-size: 10px; color: var(--ink3); width: 32px; text-align: center; }
.fmt-colors { display: inline-flex; gap: 3px; padding: 2px; border-left: 1px solid var(--border); }
.fmt-swatch {
  width: 15px;
  height: 15px;
  border: 1px solid rgba(0, 0, 0, .15);
  border-radius: 3px;
  cursor: pointer;
  padding: 0;
}
.fmt-swatch:hover { transform: scale(1.2); }
</style>
