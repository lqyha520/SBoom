<script setup lang="ts">
/**
 * 纸面富文本工具条：加粗 / 字号 / 颜色（作用于纸面内当前选区）
 * 按钮全部 mousedown.prevent——保持选区在纸面可编辑区内不丢失。
 */
import { onBeforeUnmount, onMounted } from 'vue'

let saved: Range | null = null

function onSelChange() {
  const s = document.getSelection()
  if (s && s.rangeCount && s.anchorNode) {
    const el = s.anchorNode.nodeType === 1 ? (s.anchorNode as HTMLElement) : s.anchorNode.parentElement
    if (el && el.closest('.paper')) saved = s.getRangeAt(0).cloneRange()
  }
}
onMounted(() => document.addEventListener('selectionchange', onSelChange))
onBeforeUnmount(() => document.removeEventListener('selectionchange', onSelChange))

function exec(cmd: string, val?: string) {
  const s = document.getSelection()
  const inPaper = !!(s && s.rangeCount && s.anchorNode &&
    ((s.anchorNode.nodeType === 1 ? (s.anchorNode as HTMLElement) : s.anchorNode.parentElement)?.closest('.paper')))
  if (!inPaper && saved && s) {
    s.removeAllRanges()
    s.addRange(saved)
  }
  document.execCommand(cmd, false, val)
}

function onSize(v: string) {
  if (v) exec('fontSize', v)
}
function onColor(v: string) {
  if (v) exec('foreColor', v)
}
</script>

<template>
  <span class="fmt-bar" @mousedown.prevent>
    <button class="fmt-btn" title="加粗" @click="exec('bold')"><b>B</b></button>
    <button class="fmt-btn" title="小字号" @click="onSize('1')">小</button>
    <button class="fmt-btn" title="中字号" @click="onSize('3')">中</button>
    <button class="fmt-btn" title="大字号" @click="onSize('5')">大</button>
    <button class="fmt-btn" title="特大字号" @click="onSize('7')">特大</button>
    <label class="fmt-btn fmt-color-label" title="文字颜色">
      🎨
      <input type="color" value="#d0342c" class="fmt-color-input" @change="onColor(($event.target as HTMLInputElement).value)">
    </label>
  </span>
</template>

<style scoped>
.fmt-bar { display: inline-flex; align-items: center; gap: 3px; }
.fmt-btn {
  border: 1px solid var(--border2);
  background: var(--surface);
  border-radius: 4px;
  font-size: 11px;
  padding: 2px 7px;
  color: var(--ink2);
  cursor: pointer;
  line-height: 1.5;
}
.fmt-btn:hover { border-color: var(--primary); color: var(--primary); }
.fmt-color-label { position: relative; overflow: hidden; }
.fmt-color-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
</style>
