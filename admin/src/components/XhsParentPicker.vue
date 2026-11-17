<script setup lang="ts">
import { onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import { listWorkflow, nextWorkflow, workflowLabels, workflowError, workflowStatus, type WorkflowKind, type WorkflowRecord } from '../xhs-workflow'
import { workflowSummary } from '../xhs-workflow-presentation'
import { navigateAdmin } from '../navigation'
import { workflowTabs } from '../xhs-workflow'

const props = defineProps<{ kind: WorkflowKind; next: WorkflowKind }>()
const items = ref<WorkflowRecord[]>([]), total = ref(0), page = ref(1), q = ref(''), appliedQuery = ref(''), error = ref(''), loading = ref(false)
let sequence = 0, active = true
async function load() {
  if (!active) return
  const id = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await listWorkflow(props.kind, { q: appliedQuery.value, page: page.value })
    if (id !== sequence) return
    total.value = result.total
    const last = Math.max(1, Math.ceil(result.total / 20))
    if (page.value > last) { page.value = last; return }
    items.value = result.items
  } catch (cause) { if (id === sequence) error.value = workflowError(cause) }
  finally { if (id === sequence) loading.value = false }
}
function search() {
  appliedQuery.value = q.value.trim()
  if (page.value !== 1) page.value = 1
  else void load()
}
function reset() { q.value = ''; search() }
watch(() => props.kind, () => { q.value = ''; appliedQuery.value = ''; page.value = 1 }, { flush: 'sync' })
watch([page, () => props.kind], () => { void load() })
onActivated(() => { active = true; if (!loading.value) void load() })
function deactivate() { active = false; sequence++; loading.value = false }
onDeactivated(deactivate); onUnmounted(deactivate)
void load()
</script>

<template>
  <div class="workflow-card parent-picker" :aria-busy="loading">
    <h3>选择关联{{ workflowLabels[kind] }}</h3>
    <p class="workflow-hint">先查看摘要和状态，选好后带入已有内容，继续完成下一步。</p>
    <form class="parent-search" role="search" @submit.prevent="search">
      <UInput v-model="q" placeholder="搜索已有内容，按 Enter 查找" aria-label="搜索关联内容" maxlength="120" />
      <UButton label="查找" type="submit" :loading="loading" />
      <UButton label="清空搜索" variant="ghost" :disabled="!q && !appliedQuery" @click="reset" />
    </form>
    <div class="workflow-list-meta" role="status"><span>{{ loading ? '正在读取可选内容…' : error ? '读取失败' : '共 ' + total + ' 条可选内容' }}</span><span v-if="appliedQuery">搜索：{{ appliedQuery }}</span></div>
    <UAlert v-if="error" :title="error" color="error" role="alert" />
    <div v-if="loading" class="workflow-skeletons" aria-hidden="true"><div v-for="index in 3" :key="index" class="workflow-skeleton"><span></span><div><span></span><span></span></div></div></div>
    <div v-else-if="error" class="workflow-empty-state"><p>可选内容暂时未能加载，请重试。</p><UButton label="重新加载" variant="outline" @click="load" /></div>
    <div v-else class="workflow-list">
      <button v-for="item in items" :key="item.id" type="button" class="workflow-list-item" @click="nextWorkflow(next, item.id)">
        <span class="workflow-item-copy"><strong>{{ item.title }}</strong><span class="workflow-item-summary">{{ workflowSummary(item) }}</span></span>
        <span class="workflow-status" :data-status="item.status">{{ workflowStatus(item.status) }}</span><span class="parent-select">选择 →</span>
      </button>
      <div v-if="!items.length" class="workflow-empty-state"><p>{{ appliedQuery ? '没有找到匹配的内容，试试其他关键词。' : '暂时没有可选内容，请先到' + workflowLabels[kind] + '创建。' }}</p><UButton v-if="appliedQuery" label="清空搜索" variant="outline" @click="reset" /><UButton v-else :label="`去${workflowLabels[kind]}创建`" variant="outline" @click="navigateAdmin(workflowTabs[kind], {new:'1'})" /></div>
    </div>
    <div v-if="!error && total > 20" class="workflow-pagination"><UPagination v-model:page="page" :total="total" :items-per-page="20" :disabled="loading" /></div>
  </div>
</template>

<style scoped>
.parent-search{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;margin-top:14px;align-items:center}
.parent-select{white-space:nowrap;font-size:12px;color:var(--ui-primary)}
@media(max-width:600px){.parent-search{grid-template-columns:1fr auto}.parent-search > :first-child{grid-column:1/-1}.parent-picker .workflow-list-item{flex-wrap:wrap}.parent-picker .workflow-item-copy{flex-basis:100%}}
</style>
