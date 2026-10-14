<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string }>(), { placeholder: '搜索习题' })
const emit = defineEmits<{ 'update:modelValue': [value: string]; search: []; focus: []; blur: [] }>()
</script>

<template>
  <view class="search-field" :class="{ 'has-query': !!modelValue.trim() }" role="search">
    <wd-search :model-value="modelValue" :placeholder="placeholder" :aria-label="placeholder" :maxlength="120" placeholder-left hide-cancel variant="plain" @update:model-value="emit('update:modelValue', $event)" @search="emit('search')" @focus="emit('focus')" @blur="emit('blur')">
      <template #input-suffix><wd-button icon="arrow-right" variant="text" type="info" role="button" aria-label="搜索习题" title="搜索习题" custom-class="search-submit" @click="emit('search')" /></template>
    </wd-search>
  </view>
</template>

<style scoped>
.search-field { width: 100%; min-width: 0; border: 1px solid var(--lc-card-line); border-radius: var(--lc-radius-control); background: var(--lc-surface); --wot-search-plain-block-bg: var(--lc-surface); transition: box-shadow .18s, border-color .18s; }
.search-field:focus-within { border-color: var(--lc-primary); box-shadow: 0 0 0 3px #307e6112; }
.search-field :deep(.wd-search) { border-radius: var(--lc-radius-control); overflow: hidden; }
.search-field :deep(.search-submit) { width: 44px; height: 44px; min-width: 44px; margin-left: 0; border-radius: 50%; color: var(--lc-muted); }
.search-field.has-query :deep(.search-submit) { color: var(--lc-primary); }
.search-field :deep(.wd-search__placeholder-txt) { font-size: 14px; }
</style>
