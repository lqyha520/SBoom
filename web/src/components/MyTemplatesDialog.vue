<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'
defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const search = ref('')
const pendingDelete = ref('')
const busy = ref(false)
const copying = ref('')
const copyName = ref('')
const error = ref('')
const templates = computed(() => store.myTemplates.filter(t => t.name.toLowerCase().includes(search.value.toLowerCase().trim())))
function use(name: string) {
  error.value = ''
  if (store.loadMyTemplate(name)) { store.backToBuild(); emit('close') }
  else error.value = '该模板没有可用的题目内容'
}
async function remove() {
  if (!pendingDelete.value) return
  busy.value = true
  error.value = ''
  try { await store.deleteMyTemplate(pendingDelete.value) }
  catch (e) { error.value = e instanceof Error ? e.message : '删除失败，模板仍保留' }
  finally { pendingDelete.value = ''; busy.value = false }
}
async function copy() {
  busy.value = true
  error.value = ''
  try {
    if (await store.copyMyTemplate(copying.value, copyName.value)) copying.value = ''
    else error.value = '副本保存失败'
  } catch (e) { error.value = e instanceof Error ? e.message : '另存失败' }
  finally { busy.value = false }
}
</script>

<template>
  <UModal :open="open" title="我的模板" :ui="{ content: 'max-w-2xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <div class="flex items-center gap-2"><UInput v-model="search" icon="i-lucide-search" placeholder="搜索模板" aria-label="搜索模板" class="flex-1" /><UTooltip text="同步模板"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" aria-label="同步模板" :loading="store.templatesSyncing" @click="store.syncTemplatesFromServer()" /></UTooltip></div>
      <UAlert v-if="error" :title="error" color="error" variant="soft" class="mt-4" />
      <div v-if="!templates.length" class="empty-state"><UIcon name="i-lucide-folder-open" class="size-9" /><h3>{{ search ? '没有匹配的模板' : '还没有保存的模板' }}</h3></div>
      <div v-for="template in templates" :key="template.name" class="template-row">
        <span class="template-icon"><UIcon name="i-lucide-file-text" class="size-5" /></span>
        <div class="min-w-0 flex-1">
          <h3 class="text-sm font-medium break-words">{{ template.name }}</h3>
          <p class="mt-1 text-xs text-muted break-words">{{ template.grade }} {{ template.subject }} / {{ template.cards.map(c => (TYPE_NAME[c.type] || c.type) + ' × ' + c.count).join('、') }}</p>
          <p v-if="template._syncState !== 'synced'" class="mt-1 text-xs text-warning break-words">{{ template._syncState === 'conflict' ? '版本冲突 · ' : '待同步 · ' }}{{ template._syncError || '本机版本已保留' }}</p>
        </div>
        <UTooltip v-if="template._syncState === 'conflict'" text="另存为新模板"><UButton icon="i-lucide-copy-plus" color="warning" variant="ghost" size="sm" :aria-label="'另存模板 ' + template.name" @click="copying = template.name; copyName = template.name + ' 副本'" /></UTooltip>
        <UButton label="使用" color="neutral" variant="outline" size="sm" :disabled="store.generating" @click="use(template.name)" />
        <UTooltip text="删除模板"><UButton icon="i-lucide-trash-2" color="neutral" variant="ghost" size="sm" :aria-label="'删除模板' + template.name" @click="pendingDelete = template.name" /></UTooltip>
      </div>
    </template>
  </UModal>
  <UModal :open="!!pendingDelete" title="删除模板" :description="'确定删除「' + pendingDelete + '」？本机与服务端副本都会删除，此操作无法撤销。'" @update:open="value => { if (!value) pendingDelete = '' }">
    <template #footer><UButton color="neutral" variant="outline" label="取消" :disabled="busy" @click="pendingDelete = ''" /><UButton color="error" label="确认删除" :loading="busy" @click="remove" /></template>
  </UModal>
  <UModal :open="!!copying" title="另存为新模板" @update:open="value => { if (!value && !busy) copying = '' }">
    <template #body><UFormField label="模板名称"><UInput v-model="copyName" maxlength="120" aria-label="副本名称" class="w-full" /></UFormField><UAlert v-if="error" :title="error" color="error" variant="soft" class="mt-4" /></template>
    <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="copying = ''" /><UButton icon="i-lucide-copy-plus" label="保存副本" :loading="busy" :disabled="!copyName.trim()" @click="copy" /></template>
  </UModal>
</template>

<style scoped>
.template-row { display: flex; align-items: center; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--ui-border-muted); }
.template-row:last-child { border-bottom: 0; padding-bottom: 0; }
.template-icon { background: #f0f6f3; color: #508b70; display: grid; place-items: center; width: 36px; height: 42px; border-radius: 5px; flex: none; }
@media (max-width: 480px) { .template-row { gap: 6px; } .template-icon { display: none; } }
</style>
