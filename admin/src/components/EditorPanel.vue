<script setup lang="ts">
defineProps<{ open: boolean; title: string; inline?: boolean; dismissible?: boolean; close?: boolean; ui?: Record<string, string> }>()
defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <section v-if="inline && open" class="editor-panel" :aria-label="title">
    <div class="editor-panel-body"><slot name="body" /></div>
    <div class="editor-panel-footer"><slot name="footer" /></div>
  </section>
  <UModal v-else-if="!inline" :open="open" :title="title" :dismissible="dismissible" :close="close" :ui="ui" @update:open="$emit('update:open', $event)">
    <template #body><slot name="body" /></template>
    <template #footer><slot name="footer" /></template>
  </UModal>
</template>

<style scoped>
.editor-panel-body { min-width: 0; }
.editor-panel-footer { display:flex;flex-wrap:wrap;gap:8px;margin-top:20px;padding-top:16px;border-top:1px solid var(--ui-border); }
</style>
