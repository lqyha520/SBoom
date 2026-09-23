<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { listDrafts, removeDraft, type DraftEntry } from '../persistence'
import { useExamStore } from '../stores/exam'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const entries = ref<DraftEntry[]>([])
const offset = ref(0), more = ref(false), loading = ref(false), deleting = ref(false)
const error = ref(''), pending = ref<DraftEntry | null>(null)
let sequence = 0
async function load(start = offset.value) {
  const ticket = ++sequence
  loading.value = true; error.value = ''
  try {
    const values = await listDrafts(store.ownerId, start)
    if (ticket !== sequence) return
    if (!values.length && start) { await load(Math.max(0, start - 20)); return }
    entries.value = values.slice(0, 20); more.value = values.length > 20; offset.value = start
  } catch (cause) { if (ticket === sequence) error.value = cause instanceof Error ? cause.message : '草稿读取失败' }
  finally { if (ticket === sequence) loading.value = false }
}
async function remove() {
  if (!pending.value || deleting.value) return
  deleting.value = true; error.value = ''
  try { await removeDraft(store.ownerId, pending.value, store.draftId); pending.value = null; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '草稿删除失败'; pending.value = null }
  finally { deleting.value = false }
}
watch(() => props.open, open => {
  if (open) void load(0)
  else { sequence++; loading.value = false; pending.value = null }
}, { immediate: true })
onBeforeUnmount(() => { sequence++ })
</script>

<template>
  <UModal :open="open" title="整理本机草稿" description="每个工作台页面有独立草稿。删除旧副本前请先关闭其他工作台页面；当前页面的草稿会保留。" @update:open="value => { if (!value && !deleting) emit('close') }">
    <template #body>
      <UAlert v-if="error" :title="error" color="error" role="alert" />
      <p v-if="loading" role="status">正在读取草稿…</p>
      <p v-else-if="!entries.length">没有本机草稿</p>
      <div v-for="entry in entries" :key="entry.id" class="flex items-center gap-3 border-b border-default py-3">
        <div class="flex-1 min-w-0"><p class="break-words">{{ entry.title }}</p><p class="text-xs text-muted">{{ entry.grade }} {{ entry.subject }} · {{ new Date(entry.updatedAt).toLocaleString('zh-CN') }}</p></div>
        <span v-if="entry.id === store.ownerId + ':' + store.draftId">当前页面</span>
        <UButton v-else label="删除" color="error" variant="ghost" :disabled="loading || deleting" @click="pending = entry" />
      </div>
      <div class="flex items-center justify-between mt-4">
        <UButton label="上一页" :disabled="loading || deleting || !offset" @click="load(offset - 20)" />
        <span>第 {{ Math.floor(offset / 20) + 1 }} 页</span>
        <UButton label="下一页" :disabled="loading || deleting || !more" @click="load(offset + 20)" />
      </div>
    </template>
  </UModal>
  <UModal :open="!!pending" title="删除这份旧草稿？" :description="pending?.title" @update:open="value => { if (!value && !deleting) pending = null }">
    <template #body>仅删除所选的本机草稿，不影响历史版本和云端试卷。删除后无法恢复。</template>
    <template #footer><UButton label="取消" color="neutral" :disabled="deleting" @click="pending = null" /><UButton label="确认删除" color="error" :loading="deleting" @click="remove" /></template>
  </UModal>
</template>
