<script setup lang="ts">
defineProps<{ zoom: number; manual: number }>()
defineEmits<{ change: [value: number] }>()
</script>

<template>
  <div class="zoom-control">
    <UTooltip text="适应宽度"><UButton icon="i-lucide-scan" :color="manual === 0 ? 'primary' : 'neutral'" variant="ghost" size="xs" aria-label="适应宽度" @click="$emit('change', 0)" /></UTooltip>
    <input type="range" min="25" max="100" step="5" :value="Math.round((manual || zoom) * 100)" aria-label="预览缩放比例" @input="$emit('change', Number(($event.target as HTMLInputElement).value) / 100)">
    <output class="zoom-value">{{ Math.round(zoom * 100) }}%</output>
  </div>
</template>
