<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, ref } from 'vue'
import { getUsage, type UsageAnalytics } from '../experience'
const data = ref<UsageAnalytics | null>(null)
const error = ref('')
const loading = ref(false)
let sequence = 0
const totals = computed(() => data.value?.timeline.reduce((sum, row) => ({ ok: sum.ok + row.download_ok, failed: sum.failed + row.download_failed, misses: sum.misses + row.search_miss }), { ok: 0, failed: 0, misses: 0 }))
async function load() {
  if (loading.value) return
  const current = ++sequence
  loading.value = true; error.value = ''
  try { const result = await getUsage(); if (current === sequence) data.value = result }
  catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '统计加载失败' }
  finally { if (current === sequence) loading.value = false }
}
onMounted(load)
onActivated(load)
onDeactivated(() => { sequence++; loading.value = false })
</script>
<template>
  <section class="usage-trends"><div class="section-toolbar"><h2>使用趋势</h2><UButton label="刷新使用数据" color="neutral" variant="outline" :loading="loading" @click="load" /></div><UAlert v-if="error" :title="error" color="error" /><template v-if="data"><div class="usage-metrics"><div>今日活跃<strong>{{ data.daily_active }}</strong></div><div>近 7 天活跃<strong>{{ data.weekly_active }}</strong></div><div>近 30 天活跃<strong>{{ data.monthly_active }}</strong></div><div>获取或打开 PDF 成功<strong>{{ totals?.ok }}</strong></div><div>下载失败报告<strong>{{ totals?.failed }}</strong></div></div><p class="text-sm text-muted my-4">按北京时间统计。下载结果来自客户端报告，成功不代表用户已另存文件。表格和问题排行展示最近 30 天；新功能启用前不补算历史使用行为。</p><div class="data-scroll trend-scroll"><table class="data-table"><thead><tr><th>日期</th><th>活跃用户</th><th>PDF 成功</th><th>下载失败</th><th>无结果搜索</th></tr></thead><tbody><tr v-for="row in [...data.timeline].reverse()" :key="row.date"><td>{{ row.date }}</td><td>{{ row.active_users }}</td><td>{{ row.download_ok }}</td><td>{{ row.download_failed }}</td><td>{{ row.search_miss }}</td></tr></tbody></table></div><div class="usage-problems"><div><h3>用户搜不到的内容</h3><p v-if="!data.search_misses.length">暂无无结果搜索</p><p v-for="item in data.search_misses" :key="item.query">{{ item.query }} <strong>{{ item.total }} 次</strong></p></div><div><h3>下载失败较多的资料</h3><p v-if="!data.download_failures.length">暂无下载失败报告</p><p v-for="item in data.download_failures" :key="item.catalog_id || ''">{{ item.title || '已删除资料' }} <strong>{{ item.total }} 次</strong></p></div></div></template></section>
</template>
<style scoped>
.usage-trends { margin-top:32px;border-top:1px solid var(--ui-border);padding-top:24px; }.usage-metrics { display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px;font-size:12px;color:var(--ui-text-muted); }.usage-metrics strong { display:block;font-size:26px;color:var(--ui-text);margin-top:8px; }.trend-scroll { max-height:360px; }.usage-problems { display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:24px;margin-top:24px; }.usage-problems p { font-size:13px;line-height:1.7;margin:10px 0;overflow-wrap:anywhere; }.usage-problems strong { float:right;margin-left:16px; }
</style>
