<script setup lang="ts">
import { computed } from 'vue'
import { useTabBarOverlay } from '../services/tabbar-overlay'

const props = defineProps<{
  open: boolean
  title: string
  value: string
  options: { value: string; label: string }[]
}>()
const emit = defineEmits<{ close: []; select: [value: string] }>()
const listHeight = computed(() => Math.max(0, props.options.length * 64 - 8))
useTabBarOverlay(() => props.open)
function select(value: string) {
  if (!props.open) return
  emit('select', value)
  emit('close')
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && emit('close')">
    <view class="choice-sheet" role="dialog" aria-modal="true" :aria-label="title">
      <view class="sheet-handle" />
      <view class="sheet-head">
        <text class="sheet-title">{{ title }}</text>
        <button class="bare-icon" hover-class="control-pressed" role="button" :aria-label="'关闭' + title" @click="emit('close')"><wd-icon name="close" size="20px" /></button>
      </view>
      <scroll-view scroll-y class="choice-scroll" :style="{ height: listHeight + 'px' }">
        <view class="choice-options">
          <button v-for="option in options" :key="option.value" class="choice-option" :class="{ selected: value === option.value }" hover-class="choice-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :aria-label="option.label" :aria-pressed="value === option.value" @click="select(option.value)">
            <text class="choice-label">{{ option.label }}</text>
            <view class="choice-check" :class="{ visible: value === option.value }" aria-hidden="true"><wd-icon name="check" size="16px" /></view>
          </button>
        </view>
      </scroll-view>
    </view>
  </wd-popup>
</template>

<style scoped>
.choice-sheet { max-width:520px;margin:0 auto;padding:12px 20px 24px; }
.choice-scroll { max-height:55vh; }
.choice-options { display:flex;flex-direction:column;gap:8px; }
.choice-option { display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;height:56px;margin:0;padding:8px 14px;border:1px solid var(--lc-card-line);border-radius:12px;background:var(--lc-background);color:var(--lc-text);font-size:14px;line-height:1.4;text-align:left;transition:background-color .16s,border-color .16s; }
.choice-label { display:-webkit-box;min-width:0;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:normal;overflow-wrap:anywhere; }
.choice-option.selected { border-color:#abd2b8;background:var(--lc-primary-soft);color:var(--lc-primary);font-weight:600; }
.choice-check { display:flex;align-items:center;flex:none;opacity:0; }.choice-check.visible { opacity:1; }
.choice-pressed { background:#e4efe7; }
@media (prefers-reduced-motion:reduce) { .choice-option { transition:none; } }
</style>
