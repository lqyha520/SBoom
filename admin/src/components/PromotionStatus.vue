<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ status: string; label: string }>()
const color = computed(() => {
  if (['paid', 'available', 'enabled'].includes(props.status)) return 'success'
  if (['pending', 'holding', 'draft'].includes(props.status)) return 'warning'
  if (['reviewing', 'approved', 'requested', 'statement'].includes(props.status)) return 'info'
  if (['void', 'exception', 'invalidated', 'rejected'].includes(props.status)) return 'error'
  return 'neutral'
})
</script>
<template>
  <UBadge :color="color" variant="subtle" class="promotion-status"><span aria-hidden="true" class="promotion-status-dot" />{{ label }}</UBadge>
</template>
