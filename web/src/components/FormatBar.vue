<script setup lang="ts">
/**
 * 纸面富文本工具条：加粗 / 字号滑条 / 颜色色板
 * 字号滑条统一逻辑：
 *   - 选中了纸面文字 → 调整选中文字的字号（1-7 档）
 *   - 没选中 → 调整试卷大标题的字号（60%-200%）
 * 颜色同理：选中文字改文字颜色；未选中改标题颜色。
 * 注意：所有控件 mousedown.prevent（保住选区），选区用 saved 恢复。
 * 色板为自绘 popover（不抢焦点）；"自定义"用原生 color input，
 * 但只在 change（弹窗关闭、焦点回归）时应用——input 实时应用会因
 * 系统弹窗导致浏览器失焦而静默失败。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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

/** 常用色板（含黑色；白字在白纸上不可见故不含白） */
const COLORS = [
  '#1a1a1a', '#d0342c', '#e67e22', '#f1c40f',
  '#27ae60', '#16a085', '#2980b9', '#8e44ad',
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

/** 恢复保存的选区；返回宿主元素（null = 无有效选区） */
function restoreSelection(): HTMLElement | null {
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
  return host && s && !s.isCollapsed ? host : null
}

function applyFontSize(v: number) {
  sizeVal.value = v
  const s = document.getSelection()
  const host = restoreSelection()
  if (host && s) {
    store.recordEdit('rich-text')
    host.focus({ preventScroll: true })
    document.execCommand('fontSize', false, String(v))
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

function applyColor(c: string) {
  const s = document.getSelection()
  const host = restoreSelection()
  if (host && s) {
    store.recordEdit('rich-text')
    host.focus({ preventScroll: true })
    document.execCommand('foreColor', false, c)
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

function applyBold() {
  const s = document.getSelection()
  const host = restoreSelection()
  if (host && s) {
    store.recordEdit('rich-text')
    host.focus({ preventScroll: true })
    document.execCommand('bold', false, undefined)
    host.dispatchEvent(new FocusEvent('blur'))
    onSelChange()
    refreshHasSelection()
  }
}

const SIZE_NAMES = ['', '很小', '小', '标准', '大', '更大', '特大', '最大']
const targetHint = computed(() => (hasSelection.value ? '选中文字' : '标题'))

/* ── 自绘色板 popover ── */
const paletteOpen = ref(false)
function togglePalette() {
  paletteOpen.value = !paletteOpen.value
}
function pickColor(c: string) {
  applyColor(c)
  paletteOpen.value = false
}

/* ── 自定义颜色：只在 change（选色器关闭、焦点回归浏览器）时应用 ── */
const customColor = ref('#1a1a1a')
function onCustomColor(e: Event) {
  applyColor((e.target as HTMLInputElement).value)
  paletteOpen.value = false
}

/* 点击色板外部时关闭 */
function onDocMouseDown(e: MouseEvent) {
  if (!paletteOpen.value) return
  if (!(e.target as HTMLElement).closest('.fmt-palette-wrap')) paletteOpen.value = false
}
onMounted(() => document.addEventListener('mousedown', onDocMouseDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMouseDown))
</script>

<template>
  <span class="fmt-bar">
    <UTooltip text="加粗"><button class="fmt-btn" aria-label="加粗" :disabled="!hasSelection" @mousedown.prevent @click="applyBold"><UIcon name="i-lucide-bold" class="size-4" /></button></UTooltip>
    <span class="fmt-size" :title="`字号：选中文字时改选中文字，否则改${hasSelection ? '选中文字' : '试卷标题'}`">
      <span class="fmt-size-label">{{ targetHint }}</span>
      <input
        v-if="hasSelection"
        type="range" min="1" max="7" step="1"
        :value="sizeVal"
        @input="applyFontSize(parseInt(($event.target as HTMLInputElement).value))"
        class="fmt-size-range"
        aria-label="选中文字字号"
      >
      <input
        v-else
        type="range" min="60" max="200" step="5"
        :value="Math.round((store.style.titleScale ?? 1) * 100)"
        @input="store.setStyle({ titleScale: parseInt(($event.target as HTMLInputElement).value) / 100 })"
        class="fmt-size-range"
        aria-label="试卷标题字号"
      >
      <span class="fmt-size-val">{{ hasSelection ? (SIZE_NAMES[sizeVal] || sizeVal) : Math.round((store.style.titleScale ?? 1) * 100) + '%' }}</span>
    </span>

    <!-- 颜色：自绘色板（不抢焦点，选区不丢） -->
    <span class="fmt-palette-wrap">
      <button
        class="fmt-btn fmt-color-btn"
        :title="`文字颜色（${targetHint}）：点开色板选择`"
        :class="{ on: paletteOpen }"
        :aria-expanded="paletteOpen"
        aria-label="文字颜色"
        :disabled="!hasSelection"
        @mousedown.prevent
        @click="togglePalette"
      ><UIcon name="i-lucide-palette" class="size-4" /></button>
      <div v-if="paletteOpen" class="fmt-palette" role="group" aria-label="文字颜色" @mousedown.prevent @keydown.esc="paletteOpen = false">
        <div class="fmt-pal-grid">
          <button
            v-for="c in COLORS"
            :key="c"
            class="fmt-pal-cell"
            :style="{ background: c }"
            :title="c"
            :aria-label="'颜色 ' + c"
            @click="pickColor(c)"
          ></button>
        </div>
        <label class="fmt-pal-custom" title="自定义颜色：打开系统选色器任选">
          <span class="fmt-pal-custom-dot" :style="{ background: customColor }"></span>
          自定义颜色…
          <input type="color" :value="customColor" class="fmt-pal-input" @change="onCustomColor">
        </label>
      </div>
    </span>
  </span>
</template>

<style scoped>
.fmt-bar { display: inline-flex; align-items: center; gap: 6px; }
.fmt-btn {
  border: 1px solid var(--border2);
  background: var(--surface);
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--ink2);
  cursor: pointer;
  line-height: 1.5;
}
.fmt-btn:hover, .fmt-btn.on { border-color: var(--primary); color: var(--primary); }
.fmt-btn:disabled { opacity: .4; cursor: not-allowed; }
.fmt-size { display: inline-flex; align-items: center; gap: 4px; padding: 0 4px; }
.fmt-size-label { font-size: 11px; color: var(--primary); white-space: nowrap; }
.fmt-size-range { width: 70px; accent-color: var(--primary); height: 14px; cursor: pointer; }
.fmt-size-val { font-size: 10px; color: var(--ink3); width: 32px; text-align: center; }

/* ── 色板 ── */
.fmt-palette-wrap { position: relative; display: inline-flex; }
.fmt-color-btn { font-size: 13px; line-height: 1.2; }
.fmt-palette {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 60;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 8px;
  box-shadow: var(--shadow-md);
  padding: 8px;
  width: 148px;
}
.fmt-pal-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
.fmt-pal-cell {
  height: 24px;
  border: 1px solid rgba(0, 0, 0, .12);
  border-radius: 5px;
  cursor: pointer;
  padding: 0;
}
.fmt-pal-cell:hover { transform: scale(1.12); border-color: var(--primary); }
.fmt-pal-custom {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px dashed var(--border);
  font-size: 11px;
  color: var(--ink2);
  cursor: pointer;
  position: relative;
}
.fmt-pal-custom:hover { color: var(--primary); }
.fmt-pal-custom-dot {
  width: 14px; height: 14px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, .15);
}
.fmt-pal-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
}
</style>
