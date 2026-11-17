<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getTodayTasks, type TaskCategory, type TodayTask } from '../xhs-workspace'
import { formatWorkflowDate, workflowTabs, workflowError, workflowLabels } from '../xhs-workflow'
import { adminRoute, navigateAdmin } from '../navigation'
const open = ref(false), category = ref<TaskCategory>('review'), page = ref(1), total = ref(0), items = ref<TodayTask[]>([]), loading = ref(false), error = ref('')
let sequence = 0
async function load() {
  if (!open.value) return
  const seq = ++sequence; loading.value = true; error.value = ''
  try { const result = await getTodayTasks(category.value, page.value); if (seq === sequence) { items.value = result.items; total.value = result.total } }
  catch (cause) { if (seq === sequence) error.value = workflowError(cause) }
  finally { if (seq === sequence) loading.value = false }
}
function choose(value: TaskCategory) { if (category.value === value) return; category.value = value; items.value = []; total.value = 0; if (page.value !== 1) page.value = 1; else void load() }
function continueTask(item: TodayTask) {
  const tab = category.value === 'analytics' ? 'xhsAnalytics' : workflowTabs[item.kind]
  navigateAdmin(tab, { id: item.id, ...(item.checkpoint ? { checkpoint: String(item.checkpoint) } : {}) })
  if (adminRoute.tab === tab && new URLSearchParams(adminRoute.query).get('id') === item.id) open.value = false
}
watch(open, value => { if (value) void load(); else { ++sequence; loading.value = false } }); watch(page, load)
onBeforeUnmount(() => { ++sequence })
</script>
<template>
  <UButton label="今日待办" icon="i-lucide-list-todo" variant="outline" size="sm" @click="open=true" />
  <UModal v-model:open="open" title="今日待办" :ui="{content:'max-w-3xl'}"><template #body><div class="today-tasks">
    <p class="workflow-hint">{{ new Date().toLocaleDateString('zh-CN') }} · 集中处理待完善／复核、今天及逾期待发布、已到观察时间的复盘。点击记录继续原流程。</p>
    <div class="workflow-actions"><UButton v-for="item in ([{id:'review',label:'待完善／复核'},{id:'publish',label:'今天及逾期待发布'},{id:'analytics',label:'到期待复盘'}] as const)" :key="item.id" :label="item.label" :variant="category===item.id?'solid':'ghost'" @click="choose(item.id)" /><UButton label="刷新待办" variant="ghost" :loading="loading" @click="load" /></div>
    <UAlert v-if="error" :title="error" color="error" /><p role="status">{{ loading ? '正在读取…' : `共 ${total} 项` }}</p>
    <div class="workflow-list" :inert="loading"><button v-for="item in items" :key="item.id+':'+(item.checkpoint||'')" class="workflow-list-item" :disabled="loading" @click="continueTask(item)"><div><strong>{{ item.title }}</strong><small>{{ item.checkpoint ? `发布后第 ${item.checkpoint} 天 · ${formatWorkflowDate(item.due_at!)}` : workflowLabels[item.kind] }}</small></div><span>继续 →</span></button></div>
    <p v-if="!loading && !items.length && !error" class="workflow-empty">当前没有这类待办。</p><UPagination v-if="total>20" v-model:page="page" :total="total" :items-per-page="20" :disabled="loading" />
  </div></template></UModal>
</template>
<style scoped>.today-tasks{display:grid;gap:16px}.today-tasks .workflow-list-item{width:100%;text-align:left}</style>
