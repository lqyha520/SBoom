<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
const store = useExamStore()
const confirm = ref(false)
const requests = computed(() => store.pendingRun?.jobs.flatMap(job => job.chunks.map(chunk => ({
  id: chunk.requestId, paper: job.index + 1, error: chunk.error,
}))) || [])
async function retry() { confirm.value = false; await store.retryFailed() }
</script>

<template>
  <div v-if="store.failedCount" class="recovery-actions">
    <UButton icon="i-lucide-search-check" label="查询原请求" color="neutral" variant="outline" size="xs" :loading="store.generating" @click="store.recoverPending()" />
    <UButton icon="i-lucide-refresh-cw" :label="'补齐 ' + store.failedCount + ' 份'" color="warning" variant="soft" size="xs" :disabled="store.generating" @click="confirm = true" />
  </div>
  <UModal v-model:open="confirm" title="补齐未完成的试卷" description="沿用原来的出题条件。已完成的部分不会重做；新的模型请求可能产生费用，仍在处理的请求不会重复发送。">
    <template #body>
      <p v-if="store.pendingRun" class="mb-4 text-xs text-toned break-words">{{ store.pendingRun.context.grade }} · {{ store.pendingRun.context.subject }} · {{ store.pendingRun.context.keyword }}</p>
      <dl class="space-y-3 text-xs">
        <div v-for="request in requests" :key="request.id"><dt class="font-medium">第 {{ request.paper }} 份</dt><dd class="mt-1 break-all text-muted">{{ request.id }}</dd><dd v-if="request.error" class="mt-1 break-words text-warning">{{ request.error }}</dd></div>
      </dl>
    </template>
    <template #footer><UButton label="取消" color="neutral" variant="outline" @click="confirm = false" /><UButton icon="i-lucide-refresh-cw" label="确认补齐" @click="retry" /></template>
  </UModal>
</template>

<style scoped>
.recovery-actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0; }
</style>
