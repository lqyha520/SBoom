<script setup lang="ts">
import { onActivated, ref } from 'vue'
import { fetchAdminStats, type AdminStats } from '../api'
import { catalogList } from '../catalog'
import { getRequests, getOrders } from '../growth'
import { getFeedback } from '../experience'
import { navigateAdmin } from '../navigation'

defineEmits<{ configure: [] }>()
const stats = ref<AdminStats | null>(null)
const loading = ref(false)
const error = ref('')
const tasks = ref([
  { id: 'drafts', label: '待发布草稿', count: null as number | null, loading: false, error: '' },
  { id: 'requests', label: '待处理资料需求', count: null as number | null, loading: false, error: '' },
  { id: 'feedback', label: '待处理小程序反馈', count: null as number | null, loading: false, error: '' },
  { id: 'refunds', label: '待审核退款', count: null as number | null, loading: false, error: '' },
])
async function loadTask(id: string) {
  const task = tasks.value.find(item => item.id === id)!
  if (task.loading) return
  task.loading = true; task.error = ''
  try {
    const result = await (id === 'drafts' ? catalogList('', 'draft', 0) : id === 'requests' ? getRequests('pending') : id === 'feedback' ? getFeedback('pending') : getOrders({ status: 'refund_requested' }))
    task.count = result.total
  } catch { task.error = '暂未获取' }
  finally { task.loading = false }
}
function openTask(id: string) {
  if (id === 'drafts') navigateAdmin('papers', { status: 'draft' })
  else if (id === 'requests') navigateAdmin('resourceRequests', { status: 'pending' })
  else if (id === 'feedback') navigateAdmin('supportCenter', { status: 'pending' })
  else navigateAdmin('orders', { status: 'refund_requested' })
}
function refresh() { void load(); tasks.value.forEach(task => { void loadTask(task.id) }) }
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { stats.value = await fetchAdminStats() }
  catch (e: unknown) { error.value = e instanceof Error ? e.message : '概览加载失败' }
  finally { loading.value = false }
}
onActivated(refresh)
</script>

<template>
  <section class="admin-section overview-page" aria-label="运行概览">
    <div class="section-toolbar"><h2>平台概况</h2><UTooltip text="刷新数据"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" size="sm" aria-label="刷新概览" :loading="loading" @click="refresh" /></UTooltip></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <div v-if="!stats && loading" class="overview-metrics" role="status" aria-label="正在加载概览"><USkeleton v-for="n in 4" :key="n" class="h-24 rounded-md" /></div>
    <dl v-if="stats" class="overview-metrics">
      <div><dt><UIcon name="i-lucide-users-round" class="size-4" />出题用户</dt><dd>{{ stats.users.toLocaleString() }}</dd><span>{{ stats.activeUsers }} 位启用中</span></div>
      <div><dt><UIcon name="i-lucide-files" class="size-4" />用户模板</dt><dd>{{ stats.templates.toLocaleString() }}</dd><span>已保存模板</span></div>
      <div><dt><UIcon name="i-lucide-message-square" class="size-4" />用户反馈</dt><dd>{{ stats.feedbacks.toLocaleString() }}</dd><span>{{ stats.feedbacksOob }} 条超纲反馈</span></div>
      <div><dt><UIcon name="i-lucide-activity" class="size-4" />生成请求</dt><dd>{{ stats.generationUsage?.requests.toLocaleString() ?? '—' }}</dd><span>最近 24 小时</span></div>
    </dl>
    <UAlert v-if="stats?.securityWarnings?.length" title="部署提醒" :description="stats.securityWarnings.join('；')" color="warning" variant="soft" class="notice" />
    <div class="overview-columns">
      <section class="overview-tasks" aria-label="待办事项">
        <div class="overview-section-heading"><h2>待办事项</h2><span>待处理</span></div>
        <div class="task-list">
          <article v-for="(task, index) in tasks" :key="task.id" class="task-row" :aria-busy="task.loading">
            <button type="button" class="task-action" @click="openTask(task.id)" :aria-label="task.label + ' ' + (task.count ?? '') + ' 前往处理'">
              <span class="task-icon" :class="'task-icon-' + task.id"><UIcon :name="['i-lucide-file-pen-line', 'i-lucide-folder-input', 'i-lucide-messages-square', 'i-lucide-receipt-text'][index]" class="size-5" /></span>
              <span class="task-label">{{ task.label }}</span>
              <strong :class="{ 'has-tasks': task.count }">{{ task.loading && task.count === null ? '…' : task.error ? '—' : task.count }}</strong>
              <UIcon name="i-lucide-arrow-up-right" class="size-4 task-arrow" />
            </button>
            <UButton v-if="task.error" :label="task.error + '，重试'" variant="link" size="xs" @click="loadTask(task.id)" />
          </article>
        </div>
      </section>
      <section class="overview-service" aria-label="模型服务">
        <div class="overview-section-heading"><h2>模型服务</h2><UIcon name="i-lucide-cpu" class="size-4 text-muted" /></div>
        <template v-if="stats">
          <div class="service-model"><span class="service-indicator" :class="{ configured: stats.llmConfigured }"></span><strong>{{ stats.server.model || '未配置模型' }}</strong><UBadge :color="stats.llmConfigured ? 'success' : 'warning'" variant="soft" size="sm">{{ stats.llmConfigured ? '已配置' : '待配置' }}</UBadge></div>
          <dl class="service-facts"><dt>密钥加密</dt><dd>{{ stats.server.encryption }}</dd><dt>服务版本</dt><dd>v{{ stats.server.version }}</dd><dt>管理员</dt><dd>{{ stats.admins }} 人</dd></dl>
        </template>
        <UButton icon="i-lucide-settings-2" label="模型配置" color="neutral" variant="outline" size="sm" @click="$emit('configure')" />
      </section>
    </div>
    <section v-if="stats?.generationUsage" class="usage-section" aria-label="生成用量">
      <div class="overview-section-heading"><h2>生成用量</h2><span>最近 24 小时</span></div>
      <dl class="usage-grid">
        <div><dt>已完成</dt><dd>{{ stats.generationUsage.succeeded }}</dd></div>
        <div><dt>处理中</dt><dd>{{ stats.generationUsage.running }}</dd></div>
        <div><dt>模型调用</dt><dd>{{ stats.generationUsage.model_calls }}</dd></div>
        <div><dt>输入 / 输出 Token</dt><dd class="token-count">{{ stats.generationUsage.reported_calls ? stats.generationUsage.prompt_tokens.toLocaleString() + ' / ' + stats.generationUsage.completion_tokens.toLocaleString() : '未上报' }}</dd></div>
      </dl>
      <div class="usage-caption"><span>{{ stats.generationUsage.daily_limit > 0 ? '每用户每日上限 ' + stats.generationUsage.daily_limit + ' 次' : '每用户每日请求次数不限' }}</span><UBadge v-if="stats.generationUsage.unknown" color="warning" variant="soft">结果待确认 {{ stats.generationUsage.unknown }}</UBadge><span>用量已上报 {{ stats.generationUsage.reported_calls }} 次</span></div>
    </section>
  </section>
</template>

<style scoped>
.overview-metrics { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0 0 32px;padding:8px 0 28px;border-bottom:1px solid var(--ui-border); }
.overview-metrics > div { padding:0 24px;border-right:1px solid var(--ui-border);min-width:0; }
.overview-metrics > div:first-child { padding-left:0; }
.overview-metrics > div:last-child { border-right:0; }
.overview-metrics dt { display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ui-text-muted); }
.overview-metrics dd { font-size:32px;font-weight:600;line-height:1.3;margin:14px 0 4px;font-variant-numeric:tabular-nums; }
.overview-metrics span { color:var(--ui-text-muted);font-size:12px; }
.overview-columns { display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:36px; }
.overview-section-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px; }
.overview-section-heading h2 { margin:0;font-size:14px;font-weight:600; }
.overview-section-heading > span { color:var(--ui-text-muted);font-size:11px; }
.task-row { border-bottom:1px solid var(--ui-border-muted); }
.task-row:first-child { border-top:1px solid var(--ui-border); }
.task-action { display:flex;align-items:center;gap:14px;width:100%;min-height:76px;padding:12px 4px;text-align:left; }
.task-row button:hover { background:#f8fbfa; }
.task-icon { display:grid;place-items:center;width:38px;height:38px;flex:none;background:#eaf4ef;color:#087452;border-radius:6px; }
.task-icon-requests { background:#edf3fb;color:#3267aa; }
.task-icon-feedback { background:#f1f1f5;color:#606070; }
.task-icon-refunds { background:#fbf3e2;color:#987220; }
.task-label { flex:1;font-size:13px; }
.task-row strong { font-size:18px;font-weight:600;font-variant-numeric:tabular-nums;min-width:26px;text-align:right; }
.task-row strong.has-tasks { color:var(--ui-text-highlighted); }
.task-arrow { color:var(--ui-text-muted);margin-left:8px; }
.overview-service { border-left:1px solid var(--ui-border);padding-left:32px;min-width:0; }
.service-model { display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:16px 0 8px; }
.service-model strong { font-size:14px;font-weight:600;overflow-wrap:anywhere; }
.service-indicator { width:7px;height:7px;border-radius:50%;background:var(--ui-warning);flex:none; }
.service-indicator.configured { background:var(--ui-primary); }
.service-facts { display:grid;grid-template-columns:90px minmax(0,1fr);gap:16px;margin:24px 0;font-size:12px; }
.service-facts dt { color:var(--ui-text-muted); }
.service-facts dd { margin:0;overflow-wrap:anywhere; }
.usage-section { margin-top:36px;padding-top:28px;border-top:1px solid var(--ui-border); }
.usage-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;margin:24px 0; }
.usage-grid dt { font-size:12px;color:var(--ui-text-muted); }
.usage-grid dd { margin:10px 0 0;font-size:24px;font-weight:550;font-variant-numeric:tabular-nums;overflow-wrap:anywhere; }
.usage-grid .token-count { font-size:20px; }
.usage-caption { display:flex;align-items:center;flex-wrap:wrap;gap:20px;padding:14px 0;color:var(--ui-text-muted);font-size:11px; }
@media(max-width:1050px) { .overview-columns { grid-template-columns:1fr;gap:28px; }.overview-service { border-left:0;border-top:1px solid var(--ui-border);padding:24px 0 0; } }
@media(max-width:600px) {
  .overview-metrics { grid-template-columns:repeat(2,minmax(0,1fr));gap:24px 0;padding-bottom:24px; }
  .overview-metrics > div { padding:0 16px; }.overview-metrics > div:nth-child(odd) { padding-left:0; }.overview-metrics > div:nth-child(even) { border:0; }
  .overview-metrics dd { font-size:28px; }.overview-metrics dt { gap:6px; }
  .usage-grid { grid-template-columns:repeat(2,minmax(0,1fr));gap:24px 16px; }
  .task-action { gap:10px; }.task-icon { width:34px;height:34px; }
}
</style>
