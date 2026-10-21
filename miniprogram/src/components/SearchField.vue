<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string }>(), { placeholder: '搜索习题' })
const emit = defineEmits<{ 'update:modelValue': [value: string]; search: []; focus: []; blur: [] }>()
</script>

<template>
  <view class="search-field" :class="{ 'has-query': !!modelValue.trim() }" role="search">
    <wd-search :model-value="modelValue" :placeholder="placeholder" :aria-label="placeholder" :maxlength="120" placeholder-left hide-cancel variant="plain" @update:model-value="emit('update:modelValue', $event)" @search="emit('search')" @focus="emit('focus')" @blur="emit('blur')">
      <template #input-suffix>
        <button class="search-submit" :class="{ ready: !!modelValue.trim() }" hover-class="search-submit-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="搜索习题" title="搜索习题" @click="emit('search')"><wd-icon name="arrow-right" size="15px" /></button>
      </template>
    </wd-search>
  </view>
</template>

<style scoped>
.search-field { width: 100%; min-width: 0; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-surface); --wot-search-plain-block-bg: var(--lc-surface); transition: box-shadow .18s, border-color .18s; }
.search-field:focus-within { border-color: var(--lc-primary); box-shadow: 0 0 0 3px #307e6112; }
.search-field :deep(.wd-search) { border-radius: 14px; overflow: hidden; }
.search-submit { display: flex; align-items: center; justify-content: center; flex: none; width: 34px; height: 34px; margin: 0 4px 0 2px; padding: 0; border: 0; border-radius: 10px; background: transparent; color: #5d7d68; line-height: 1; transition: background-color .16s, color .16s, transform .16s, box-shadow .16s; }
.search-submit.ready { background: var(--lc-primary); color: #fff; box-shadow: 0 2px 6px #307e6129; }
.search-submit-pressed { transform: scale(.92); }
.search-field.has-query :deep(.wd-search__clear-icon) { margin-left: 2px; }
.search-field :deep(.wd-search__placeholder-txt) { font-size: 14px; }
@media (prefers-reduced-motion: reduce) { .search-submit { transition: none; } }
</style>
