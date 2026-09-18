<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import type { GenerationJob } from '../generation'
const store = useExamStore()
const expanded = ref(false), now = ref(Date.now())
const timer = setInterval(() => { if (store.generating) now.value = Date.now() }, 1000)
onBeforeUnmount(() => clearInterval(timer))
const jobs = computed(() => store.generationJobs.length ? store.generationJobs : store.pendingRun?.jobs || [])
function status(job: GenerationJob) {
  if (job.error) return job.error.includes('停止') ? '已停止' : job.chunks.some(chunk => chunk.state === 'unknown') ? '等待确认' : '失败'
  if (job.finishedAt) return '已完成'
  if (job.chunks.some(chunk => chunk.state === 'unknown')) return '等待确认'
  if (job.chunks.some(chunk => chunk.state === 'failed')) return '失败'
  if (job.startedAt || job.chunks.some(chunk => chunk.state === 'running')) return '处理中'
  return store.stopRequested ? '已停止' : '排队中'
}
function duration(job: GenerationJob) { return job.startedAt ? Math.max(0, Math.round(((job.finishedAt || now.value) - job.startedAt) / 1000)) + ' 秒' : '尚未开始' }
</script>
<template>
  <div v-if="jobs.length" class="my-3 text-xs no-print">
    <div class="flex gap-2 items-center"><UButton :label="(expanded ? '收起' : '查看') + '生成任务（' + jobs.length + '）'" variant="link" size="xs" @click="expanded = !expanded" /><UButton v-if="store.generating" :label="store.stopRequested ? '正在停止后续任务' : '停止后续任务'" color="warning" variant="soft" size="xs" :disabled="store.stopRequested" @click="store.stopRequested = true; expanded = true" /></div>
    <p v-if="store.stopRequested" class="text-warning mt-2" role="status">已发送的请求仍会完成并可能计费；未发送部分已停止，可通过补齐继续。</p>
    <ol v-if="expanded" class="mt-2 max-h-52 overflow-auto space-y-2" aria-label="生成任务列表"><li v-for="job in jobs" :key="job.index"><span>第 {{ job.index + 1 }} 份 · {{ status(job) }} · {{ duration(job) }}</span><p v-if="job.error || job.chunks.some(chunk => chunk.error)" class="text-warning break-words">{{ job.error || job.chunks.find(chunk => chunk.error)?.error }}</p></li></ol>
  </div>
</template>
