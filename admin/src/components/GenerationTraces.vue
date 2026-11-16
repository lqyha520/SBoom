<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchGenerationTraces, type GenerationTraceRow } from '../api'
import { generationPhase } from '../../../shared/generation-trace'
const rows = ref<GenerationTraceRow[]>([]), query = ref(''), error = ref(''), loading = ref(false)
const selected = ref<GenerationTraceRow | null>(null)
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { rows.value = (await fetchGenerationTraces(query.value.trim())).requests }
  catch (e) { error.value = e instanceof Error ? e.message : '追踪加载失败' }
  finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <section class="admin-section" aria-label="出题追踪">
    <div class="section-toolbar"><h2>出题追踪</h2><form class="actions-row" @submit.prevent="load"><UInput v-model="query" placeholder="请求编号（留空查看最近 30 次）" aria-label="请求编号" class="w-80" /><UButton type="submit" label="查询" :loading="loading" /></form></div>
    <UAlert v-if="error" :title="error" color="error" role="alert" />
    <p class="text-sm text-muted mb-3">模型调用次数来自实际请求；重放只返回已有结果。升级前的请求没有阶段追踪。</p>
    <div class="overflow-auto"><table class="w-full text-sm"><thead><tr><th>时间 / 请求</th><th>账号</th><th>状态</th><th>模型调用</th><th>缓存重放</th><th>实际模型</th><th>详情</th></tr></thead><tbody>
      <tr v-for="row in rows" :key="row.user_id + ':' + row.request_id"><td>{{ new Date(row.created_at * 1000).toLocaleString() }}<br><code>{{ row.request_id }}</code></td><td>{{ row.user_id }}</td><td>{{ generationPhase[row.status] || row.status }}</td><td>{{ row.model_calls }}</td><td>{{ row.replay_count }}</td><td>{{ row.trace ? [...new Set(row.trace.calls.map(call => call.model))].join('、') || '尚未调用' : '历史记录未采集' }}</td><td><UButton label="查看" variant="link" @click="selected = row" /></td></tr>
    </tbody></table></div>
    <UModal :open="!!selected" title="生成详情" @update:open="value => { if (!value) selected = null }"><template #body><div v-if="selected" class="space-y-3">
      <p>请求 {{ selected.request_id }} · {{ selected.kind }}</p><p>用量已上报 {{ selected.reported_calls }}/{{ selected.model_calls }} 次 · 输入 {{ selected.prompt_tokens }} / 输出 {{ selected.completion_tokens }} token</p>
      <template v-if="selected.trace"><p>耗时 {{ (selected.trace.elapsed_ms / 1000).toFixed(1) }} 秒</p><ul><li v-for="(stage, index) in selected.trace.stages" :key="index">{{ generationPhase[stage.stage] || stage.stage }}：{{ (stage.duration_ms / 1000).toFixed(1) }} 秒 · {{ stage.status }}</li></ul><ul><li v-for="(call, index) in selected.trace.calls" :key="index">{{ index + 1 }}. {{ call.model }} · {{ generationPhase[call.stage] || call.stage }} · {{ call.status }} · {{ call.duration_ms == null ? '处理中' : (call.duration_ms / 1000).toFixed(1) + ' 秒' }}</li></ul><p v-if="!selected.trace.rejections.length">无已记录的剔题原因</p><ul v-else><li v-for="(reason, index) in selected.trace.rejections" :key="index">{{ reason.reason }} · {{ reason.count }} 道</li></ul></template><p v-else>该历史请求未采集追踪，不代表未使用模型。</p>
    </div></template></UModal>
  </section>
</template>
