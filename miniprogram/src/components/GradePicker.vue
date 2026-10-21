<script setup lang="ts">
import { computed } from 'vue'
import { useTabBarOverlay } from '../services/tabbar-overlay'
const props = defineProps<{ open: boolean; value: string; options: string[] }>()
const emit = defineEmits<{ close: []; select: [value: string] }>()
const grades = computed(() => [...new Set(props.options)])
useTabBarOverlay(() => props.open)
function select(value: string) { emit('select', value); emit('close') }
</script>
<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet" aria-role="dialog" role="dialog" aria-modal="true" aria-label="选择年级">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">选择年级</text><button role="button" class="bare-icon" aria-label="关闭年级选择" hover-class="control-pressed" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <scroll-view scroll-y class="grade-scroll"><view class="grade-choices">
        <button role="button" class="grade-choice" :class="{ selected: !value }" :aria-pressed="!value" hover-class="control-pressed" @click="select('')">全部年级</button>
        <button role="button" v-for="grade in grades" :key="grade" class="grade-choice" :class="{ selected: value === grade }" :aria-pressed="value === grade" hover-class="control-pressed" @click="select(grade)">{{ grade }}</button>
      </view></scroll-view>
    </view>
  </wd-popup>
</template>
<style scoped>
.grade-scroll { height:55vh;max-height:440px; }
.grade-choices { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px; }
.grade-choice { display:flex;align-items:center;justify-content:center;width:100%;min-height:48px;margin:0;padding:10px 12px;font-size:14px;line-height:1.5;background:var(--lc-background);color:var(--lc-text);border:1px solid transparent;border-radius:12px;white-space:normal; }
.grade-choice.selected { color:var(--lc-primary);background:var(--lc-primary-soft);border-color:var(--lc-primary); }
</style>
