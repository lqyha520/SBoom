<script setup lang="ts">
import { useExamStore } from '../stores/exam'
import { TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType } from '../types'

const store = useExamStore()
defineEmits<{ custom: [] }>()
const icons: Record<string, string> = {
  oral_math: 'i-lucide-calculator', quiz: 'i-lucide-list-checks', fill_blank: 'i-lucide-text-cursor-input',
  true_false: 'i-lucide-circle-check', match_pair: 'i-lucide-git-compare-arrows', reading: 'i-lucide-book-open',
  word_problem: 'i-lucide-message-square-text', vertical_calc: 'i-lucide-align-vertical-justify-end',
  recursive_calc: 'i-lucide-list-ordered', smart_calc: 'i-lucide-lightbulb', number_split: 'i-lucide-git-fork',
  compare: 'i-lucide-equal', challenge: 'i-lucide-flag',
}
function add(type: string | CustomType) {
  if (typeof type === 'string') store.addSection(type, TYPE_DEFAULT[type] || 4)
  else store.addSection(type.baseType, type.defaultCount, type.name)
}
</script>

<template>
  <div class="type-picker">
    <div v-for="([label, types], index) in store.typeGroups" :key="index" class="type-group">
      <div class="type-group-label">{{ label }}</div>
      <div class="type-grid">
        <button v-for="type in types" :key="typeof type === 'string' ? type : type.id" class="type-option" :disabled="store.generating" @click="add(type)">
          <UIcon :name="icons[typeof type === 'string' ? type : type.baseType] || 'i-lucide-list'" class="size-4" />
          <span>{{ typeof type === 'string' ? TYPE_NAME[type] || type : type.name }}</span>
          <UIcon name="i-lucide-plus" class="type-plus size-3" />
        </button>
      </div>
    </div>
    <UButton icon="i-lucide-plus" label="自定义题型" color="neutral" variant="ghost" size="xs" :disabled="store.generating" @click="$emit('custom')" />
  </div>
</template>

<style scoped>
.type-picker { padding: 0 20px 12px; }
.type-group { margin-bottom: 12px; }
.type-group-label { color: var(--ui-text-muted); font-size: 11px; margin: 0 0 8px; }
.type-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.type-option { min-width: 0; display: flex; align-items: center; gap: 7px; padding: 8px; border: 1px solid var(--ui-border); border-radius: 6px; background: #fff; color: var(--ui-text-toned); text-align: left; font-size: 12px; min-height: 36px; }
.type-option > span:first-child { color: #7b8991; flex: none; }
.type-option > span:nth-child(2) { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.type-plus { color: #a7b2b9; flex: none; }
.type-option:hover:not(:disabled) { border-color: #a2ceb9; background: #f4faf7; color: #087f5b; }
.type-option:disabled { opacity: .5; }
@media (min-width: 620px) and (max-width: 899px) { .type-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
</style>
