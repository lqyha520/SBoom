<script setup lang="ts">
/**
 * 纸面富文本工具条：加粗 / 字号滑条 / 颜色（作用于纸面内当前选区）
 * - mousedown.prevent 防止点按钮时选区丢失
 * - 颜色用预设色板（原生 color input 会开对话框导致选区和焦点丢失）
 * - exec 后对选区所在的 contenteditable 元素派发 blur，立即回写数据
 */
import { ref, onBeforeUnmount, onMounted } from 'vue'

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

function exec(cmd: string, val?: string) {
  const s = document.getSelection()
  let host: HTMLElement | null = null
  if (s && s.rangeCount) host = editableHostOf(s.anchorNode)
  if (!host && saved && s) {
    // 选区丢失（点按钮瞬间）：恢复保存的选区
    host = editableHostOf(saved.startContainer)
    if (host) {
      s.removeAllRanges()
      s.addRange(saved)
    }
  }
  if (!host) return
  host.focus({ preventScroll: true })
  document.execCommand(cmd, false, val)
  // 立即回写：手动派发 blur 事件触发数据同步
  host.dispatchEvent(new FocusEvent('blur'))
  // 更新保存的选区（样式已应用）
  onSelChange()
}

/** 字号滑条（execCommand fontSize 只有 1-7 档：1=x-small 2=small 3=中 4=large 5=x-large 6/7=更大） */
const sizeVal = ref(3)
function onSizeSlider(v: number) {
  sizeVal.value = v
  exec('fontSize', String(v))
}
const SIZE_NAMES = ['', '很小', '小', '标准', '大', '更大', '特大', '最大']
</script>

<template>
  <span class="fmt-bar" @mousedown.prevent>
    <button class="fmt-btn" title="加粗" @click="exec('bold')"><b>B</b></button>
    <span class="fmt-size" title="字号">
      <span class="fmt-size-label">字号</span>
      <input
        type="range" min="1" max="7" step="1"
        :value="sizeVal"
        @input="onSizeSlider(parseInt(($event.target as HTMLInputElement).value))"
        class="fmt-size-range"
      >
      <span class="fmt-size-val">{{ SIZE_NAMES[sizeVal] || sizeVal }}</span>
    </span>
    <span class="fmt-colors" title="文字颜色">
      <button
        v-for="c in COLORS"
        :key="c"
        class="fmt-swatch"
        :style="{ background: c }"
        :title="c"
        @click="exec('foreColor', c)"
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
.fmt-size-label { font-size: 11px; color: var(--ink3); }
.fmt-size-range { width: 70px; accent-color: var(--primary); height: 14px; cursor: pointer; }
.fmt-size-val { font-size: 10px; color: var(--ink3); width: 26px; text-align: center; }
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
