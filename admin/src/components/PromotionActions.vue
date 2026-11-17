<script setup lang="ts">
defineProps<{ items: { label: string; icon?: string; color?: 'error'; onSelect: () => unknown }[]; disabled?: boolean; label?: string }>()
</script>
<template>
  <UDropdownMenu v-if="items.length" :items="items" :content="{ align: 'end' }">
    <UButton :aria-label="label || '更多操作'" label="更多" icon="i-lucide-ellipsis" color="neutral" variant="ghost" size="sm" :disabled="disabled" />
  </UDropdownMenu>
</template>
