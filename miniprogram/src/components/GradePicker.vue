<script setup lang="ts">
import { computed } from 'vue'
import { useTabBarOverlay } from '../services/tabbar-overlay'
const props = defineProps<{ open: boolean; value: string; options: string[] }>()
const emit = defineEmits<{ close: []; select: [value: string] }>()
const grades = computed(() => [...new Set(props.options)])
const listHeight = computed(() => (1 + Math.ceil(grades.value.length / 2)) * 52 + Math.ceil(grades.value.length / 2) * 10)
useTabBarOverlay(() => props.open)
function select(value: string) { emit('select', value); emit('close') }
</script>
<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet" aria-role="dialog" role="dialog" aria-modal="true" aria-label="选择年级">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">选择年级</text><button role="button" class="bare-icon" aria-label="关闭年级选择" hover-class="control-pressed" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <text class="grade-hint">选择后直接显示对应习题</text>
      <scroll-view scroll-y class="grade-scroll" :style="{ height: listHeight + 'px' }"><view class="grade-choices">
        <button role="button" class="grade-choice all-grades" :class="{ selected: !value }" :aria-pressed="!value" hover-class="grade-pressed" @click="select('')"><text>全部年级</text><view class="grade-check" :class="{ visible: !value }" aria-hidden="true"><wd-icon name="check" size="16px" /></view></button>
        <button role="button" v-for="grade in grades" :key="grade" class="grade-choice" :class="{ selected: value === grade }" :aria-pressed="value === grade" :aria-label="grade" hover-class="grade-pressed" @click="select(grade)"><text>{{ grade }}</text><view class="grade-check" :class="{ visible: value === grade }" aria-hidden="true"><wd-icon name="check" size="16px" /></view></button>
      </view></scroll-view>
    </view>
  </wd-popup>
</template>
<style scoped>
.grade-hint { display:block;margin:-4px 0 16px;font-size:13px;line-height:1.7;color:var(--lc-secondary); }
.grade-scroll { max-height:55vh; }
.grade-choices { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px; }
.grade-choice { display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;height:52px;margin:0;padding:0 14px;font-size:14px;line-height:1.5;background:var(--lc-background);color:var(--lc-text);border:1px solid var(--lc-card-line);border-radius:12px;transition:background-color .16s,border-color .16s; }
.grade-choice text { min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.all-grades { grid-column:1 / -1; }
.grade-choice.selected { color:var(--lc-primary);background:var(--lc-primary-soft);border-color:#abd2b8;font-weight:600; }
.grade-check { flex:none;display:flex;align-items:center;opacity:0; }.grade-check.visible { opacity:1; }
.grade-pressed { background:#e4efe7; }
@media (prefers-reduced-motion:reduce) { .grade-choice { transition:none; } }
</style>
