<script setup lang="ts">
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
</script>

<template>
  <view class="search-grade-row">
    <view class="grow"><SearchField :model-value="modelValue" :placeholder="placeholder" @update:model-value="emit('update:modelValue', $event)" @search="emit('search')" @focus="emit('focus')" @blur="emit('blur')" /></view>
    <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="search-grade-choice" role="button" aria-label="选择年级" :disabled="disabled" @click="emit('selectGrade')"><text>{{ grade.replace(/^小学/, '') || '全部年级' }}</text><wd-icon name="down" size="11px" /></button>
  </view>
</template>

<style scoped>
.search-grade-row { display:flex;align-items:center;gap:8px; }
.search-grade-choice { display:flex;align-items:center;justify-content:space-between;gap:4px;flex:none;width:96px;min-height:46px;margin:0;padding:0 10px;border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-control);background:var(--lc-primary-soft);color:var(--lc-primary);font-size:13px;line-height:1.5; }
.search-grade-choice text { min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.search-grade-choice[disabled] { opacity:.6; }
@media (max-width:359px) { .search-grade-row { gap:6px; }.search-grade-choice { width:88px;padding:0 8px;font-size:12px; } }
</style>
