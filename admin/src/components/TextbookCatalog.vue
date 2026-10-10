<script setup lang="ts">
import { ref, watch } from 'vue'
import { request } from '../api'
import type { ApiSchemas } from '../../../shared/api-schema'

const props = defineProps<{ grade: string; subject: string }>()
const scope = ref<ApiSchemas['KnowledgeScope'] | null>(null)
const loading = ref(false)
const error = ref('')
let revision = 0
async function load() {
  const current = ++revision
  scope.value = null
  error.value = ''
  loading.value = false
  if (!props.grade || !props.subject) return
  loading.value = true
  try {
    const params = new URLSearchParams({ grade: props.grade, subject: props.subject })
    const value = await request<ApiSchemas['KnowledgeScope']>('/api/v1/scope?' + params)
    if (current === revision) scope.value = value
  } catch (cause) {
    if (current === revision) error.value = cause instanceof Error ? cause.message : '教材目录加载失败'
  } finally {
    if (current === revision) loading.value = false
  }
}
watch(() => [props.grade, props.subject], load, { immediate: true })
</script>

<template>
  <div aria-label="人教版教材目录" :aria-busy="loading">
    <p v-if="loading" role="status">正在加载教材目录</p>
    <UAlert v-else-if="error" :title="error" color="error" :actions="[{ label: '重试', onClick: load }]" />
    <template v-else>
      <section v-for="book in scope?.books || []" :key="book.id" class="textbook-section">
        <h3>{{ book.series }} · {{ book.semester }}</h3>
        <p><a :href="book.source_url" target="_blank" rel="noopener noreferrer">官方教材 {{ book.id }}</a> · 核对日期 {{ book.verified_on }}</p>
        <div class="data-scroll"><table class="data-table"><thead><tr><th>单元</th><th>教材页码</th><th>已核对细分项</th></tr></thead>
          <tbody><tr v-for="unit in book.units" :key="unit.title"><td>{{ unit.title }}</td><td>{{ unit.page }}</td><td>{{ unit.topics?.join('、') || '单元范围' }}</td></tr></tbody>
        </table></div>
      </section>
      <p v-if="!scope?.books?.length">该教材目录尚未核实</p>
    </template>
  </div>
</template>

<style scoped>
.textbook-section { padding: 16px 0; border-bottom: 1px solid var(--ui-border); }
h3 { margin: 0 0 8px; font-size: 15px; }
p { font-size: 12px; color: var(--ui-text-muted); }
a { color: var(--ui-primary); }
</style>
