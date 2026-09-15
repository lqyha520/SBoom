<script setup lang="ts">
import { ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { MAX_QUESTIONS_PER_TYPE, TYPE_NAME } from '../constants'

const open = defineModel<boolean>('open', { default: false })
const store = useExamStore()
const name = ref('')
const base = ref('fill_blank')
const count = ref(5)
const baseTypes = Object.entries(TYPE_NAME).map(([value, label]) => ({ value, label }))
function add() {
  if (!name.value.trim()) return
  store.addCustomType(name.value.trim(), base.value, Math.min(MAX_QUESTIONS_PER_TYPE, Math.max(1, count.value || 5)))
  name.value = ''
  open.value = false
}
</script>

<template>
  <UModal v-model:open="open" title="自定义题型">
    <template #body>
      <form id="custom-type-form" class="field-stack" @submit.prevent="add">
        <UFormField label="题型名称" required><UInput v-model="name" maxlength="10" placeholder="例如：口算天天练" autofocus /></UFormField>
        <UFormField label="基础题型"><USelect v-model="base" :items="baseTypes" /></UFormField>
        <UFormField label="默认题数"><UInputNumber v-model="count" :min="1" :max="MAX_QUESTIONS_PER_TYPE" class="w-36" /></UFormField>
      </form>
      <div v-if="store.customTypes.length" class="mt-6 border-t border-default pt-4">
        <p class="mb-2 text-xs text-muted">已添加的题型</p>
        <div v-for="type in store.customTypes" :key="type.id" class="row-between py-2">
          <div class="min-w-0"><p class="text-sm font-medium break-words">{{ type.name }}</p><p class="text-xs text-muted">{{ TYPE_NAME[type.baseType] || type.baseType }} / {{ type.defaultCount }} 题</p></div>
          <UTooltip :text="'删除' + type.name"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除' + type.name" @click="store.removeCustomType(type.id)" /></UTooltip>
        </div>
      </div>
    </template>
    <template #footer><UButton color="neutral" variant="outline" label="取消" @click="open = false" /><UButton type="submit" form="custom-type-form" icon="i-lucide-plus" label="添加题型" :disabled="!name.trim()" /></template>
  </UModal>
</template>
