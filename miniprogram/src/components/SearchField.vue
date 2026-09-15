<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string }>(), { placeholder: '搜索习题' })
const emit = defineEmits<{ 'update:modelValue': [value: string]; search: [] }>()
</script>

<template>
  <view class="search-field" role="search">
    <wd-search :model-value="modelValue" :placeholder="placeholder" :aria-label="placeholder" :maxlength="120" placeholder-left hide-cancel variant="plain" @update:model-value="emit('update:modelValue', $event)" @search="emit('search')">
      <template #input-suffix><wd-button icon="arrow-right" variant="text" type="info" role="button" aria-label="搜索习题" title="搜索习题" custom-class="search-submit" @click="emit('search')" /></template>
    </wd-search>
  </view>
</template>

<style scoped>
.search-field { width: 100%; min-width: 0; border-radius: 999px; transition: box-shadow .18s; }
.search-field:focus-within { box-shadow: 0 0 0 3px #307e6112; }
.search-field :deep(.wd-search) { border-radius: 999px; overflow: hidden; }
.search-field :deep(.search-submit) { width: 44px; height: 44px; min-width: 44px; margin-left: 0; border-radius: 50%; color: var(--lc-muted); }
.search-field :deep(.wd-search__placeholder-txt) { font-size: 12px; }
</style>
