<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import type { HistoryReason } from '../persistence'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const search = ref('')
const pendingRestore = ref('')
const pendingDelete = ref('')
const busy = ref(false)
const error = ref('')
const entries = computed(() => {
  const query = search.value.trim().toLowerCase()
  return store.history.filter(entry => [entry.title, entry.grade, entry.subject, entry.keyword].join(' ').toLowerCase().includes(query))
})
const reasons: Record<HistoryReason, string> = { manual: '手动保存', generated: '生成完成', 'before-restore': '恢复前版本', 'before-generate': '重新生成前' }
const formatTime = (value: number) => new Date(value).toLocaleString('zh-CN', { hour12: false })
onMounted(() => store.refreshHistory())
async function save() {
  error.value = ''
  if (!await store.saveVersion()) error.value = store.storageError || '暂时无法保存版本'
}
async function restore() {
  error.value = ''
  if (await store.restoreHistory(pendingRestore.value)) { pendingRestore.value = ''; emit('close') }
  else { pendingRestore.value = ''; error.value = store.storageError || '恢复失败，当前内容未替换' }
}
async function remove() {
  busy.value = true
  error.value = ''
  try { await store.deleteHistory(pendingDelete.value); pendingDelete.value = '' }
  catch { error.value = '删除失败，历史版本仍保留'; pendingDelete.value = '' }
  finally { busy.value = false }
}
</script>

<template>
  <UModal :open="open" title="本机历史" :ui="{ content: 'max-w-2xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <div class="history-toolbar">
        <UInput v-model="search" icon="i-lucide-search" placeholder="搜索试卷" aria-label="搜索历史版本" class="flex-1" />
        <UButton icon="i-lucide-save" label="保存版本" :loading="store.historyBusy" :disabled="store.generating || store.layoutMode || !store.sections.length" @click="save" />
      </div>
      <UAlert v-if="error" :title="error" color="error" variant="soft" class="mt-4" role="alert" />
      <div v-if="!entries.length" class="empty-state"><UIcon name="i-lucide-history" class="size-9" /><h3>{{ search ? '没有匹配的版本' : '还没有历史版本' }}</h3></div>
      <div class="history-list">
        <article v-for="entry in entries" :key="entry.id" class="history-row">
          <UIcon name="i-lucide-file-clock" class="size-5 shrink-0 text-secondary" />
          <div class="history-detail">
            <h3>{{ entry.title }}</h3>
            <p>{{ entry.grade }} {{ entry.subject }} · {{ entry.paperCount || 1 }} 份 · {{ entry.questionCount }} 题</p>
            <p>{{ formatTime(entry.updatedAt) }} · {{ reasons[entry.reason] }}</p>
          </div>
          <UButton label="恢复" color="neutral" variant="outline" size="sm" :disabled="store.generating || store.historyBusy || store.layoutMode" :aria-label="'恢复版本 ' + entry.title" @click="pendingRestore = entry.id" />
          <UTooltip text="删除版本"><UButton icon="i-lucide-trash-2" color="neutral" variant="ghost" size="sm" :aria-label="'删除版本 ' + entry.title" :disabled="busy || store.historyBusy" @click="pendingDelete = entry.id" /></UTooltip>
        </article>
      </div>
    </template>
  </UModal>
  <UModal :open="!!pendingRestore" title="恢复历史版本" description="当前内容会先保存为恢复前版本，然后切换到所选版本。" @update:open="value => { if (!value && !store.historyBusy) pendingRestore = '' }">
    <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="store.historyBusy" @click="pendingRestore = ''" /><UButton icon="i-lucide-rotate-ccw" label="确认恢复" :loading="store.historyBusy" @click="restore" /></template>
  </UModal>
  <UModal :open="!!pendingDelete" title="删除历史版本" description="仅删除所选的本机历史记录，不影响当前试卷。删除后无法恢复。" @update:open="value => { if (!value && !busy) pendingDelete = '' }">
    <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="pendingDelete = ''" /><UButton icon="i-lucide-trash-2" label="确认删除" color="error" :loading="busy" @click="remove" /></template>
  </UModal>
</template>

<style scoped>
.history-toolbar { display: flex; align-items: center; gap: 10px; }
.history-list { max-height: min(60vh, 520px); overflow-y: auto; }
.history-row { display: flex; align-items: center; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--ui-border-muted); }
.history-detail { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.history-detail h3 { margin: 0; font-size: 14px; font-weight: 600; }
.history-detail p { margin: 4px 0 0; font-size: 11px; color: var(--ui-text-muted); }
@media (max-width: 480px) { .history-row { gap: 6px; } .history-row > .shrink-0 { display: none; } }
</style>
