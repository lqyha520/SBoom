<script setup lang="ts">
import { useAdminRefresh } from '../admin-page'
import { useAdminListRoute } from '../navigation'
import { onMounted, ref, watch } from 'vue'
import { fetchAdminLogs } from '../api'

const logs = ref('')
const lines = ref(200)
const loading = ref(false)
const error = ref('')
const choices = [100, 200, 500, 1000].map(value => ({ label: value + ' 行', value }))
let request = 0
async function load() {
  const id = ++request
  loading.value = true
  error.value = ''
  try {
    const value = await fetchAdminLogs(lines.value)
    if (id === request) logs.value = value
  } catch (e: unknown) {
    if (id === request) error.value = e instanceof Error ? e.message : '日志加载失败'
  } finally { if (id === request) loading.value = false }
}
watch(lines, load)
useAdminRefresh(load, () => { request++; loading.value = false })
const routeState = useAdminListRoute('logs', { lines }, () => { void load() })
</script>

<template>
  <section class="admin-section" aria-label="系统日志">
    <div class="section-toolbar"><h2 class="font-mono">server.log</h2><div class="actions-row"><USelect v-model="lines" :items="choices" aria-label="日志行数" class="w-28" /><UTooltip text="刷新日志"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" :loading="loading" aria-label="刷新日志" @click="load" /></UTooltip></div></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <pre class="log-view" :aria-busy="loading" tabindex="0" aria-label="服务日志内容">{{ logs || (loading ? '正在加载日志...' : error ? '日志暂不可用' : '暂无日志') }}</pre>
  </section>
</template>
