<script setup lang="ts">
import { ref } from 'vue'
import SearchField from './SearchField.vue'

withDefaults(defineProps<{
  modelValue: string
  grade: string
  placeholder?: string
  disabled?: boolean
}>(), { placeholder: '搜索习题', disabled: false })

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: []
  focus: []
  blur: []
  selectGrade: []
}>()

const focused = ref(false)
function onFocus() { focused.value = true; emit('focus') }
function onBlur() { focused.value = false; emit('blur') }
</script>

<template>
  <view class="search-grade-row" :class="{ focused, disabled }" role="group" aria-label="搜索与年级筛选">
    <view class="search-grade-field"><SearchField :model-value="modelValue" :placeholder="placeholder" @update:model-value="emit('update:modelValue', $event)" @search="emit('search')" @focus="onFocus" @blur="onBlur" /></view>
    <view class="search-grade-divider" aria-hidden="true" />
    <button hover-class="search-grade-pressed" :hover-start-time="0" :hover-stay-time="80" class="search-grade-choice" role="button" aria-label="选择年级" :disabled="disabled" @click="emit('selectGrade')"><text>{{ grade.replace(/^小学/, '') || '全部年级' }}</text><wd-icon name="down" size="10px" /></button>
  </view>
</template>

<style scoped>
.search-grade-row { display:flex;align-items:center;padding:0 4px 0 0;border:1px solid var(--lc-card-line);border-radius:14px;background:var(--lc-surface);box-shadow:0 1px 2px #23392d08;transition:border-color .18s ease,box-shadow .18s ease; }
.search-grade-row.focused { border-color:var(--lc-primary);box-shadow:0 0 0 3px #307e6112; }
.search-grade-field { flex:1;min-width:0; }
.search-grade-row :deep(.search-field) { border:0;border-radius:14px 0 0 14px;background:transparent;box-shadow:none; }
.search-grade-row :deep(.search-field:focus-within) { box-shadow:none; }
.search-grade-row :deep(.wd-search) { border-radius:0; }
.search-grade-divider { flex:none;width:1px;height:20px;margin:0 2px;background:var(--lc-card-line); }
.search-grade-choice { display:flex;align-items:center;gap:5px;flex:none;max-width:104px;min-height:44px;margin:0;padding:0 8px 0 11px;border:0;border-radius:10px;background:transparent;color:var(--lc-primary);font-size:13px;font-weight:600;line-height:1.4; }
.search-grade-choice text { min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.search-grade-choice[disabled] { opacity:.55; }
.search-grade-pressed { background:var(--lc-primary-soft); }
@media (max-width:359px) { .search-grade-choice { max-width:90px;padding:0 6px 0 9px;font-size:12.5px; } }
</style>
