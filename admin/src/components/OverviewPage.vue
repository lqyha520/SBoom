<script setup lang="ts">
import { computed, onActivated, ref } from 'vue'
import { fetchAdminStats, type AdminStats, type UserInfo } from '../api'
import { catalogList } from '../catalog'
import { getRequests, getOrders } from '../growth'
import { getFeedback } from '../experience'
import { navigateAdmin } from '../navigation'

defineEmits<{ configure: [] }>()
defineProps<{ user?: UserInfo }>()
const dateLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const stats = ref<AdminStats | null>(null)
const loading = ref(false)
const error = ref('')
const updatedAt = ref('')
const usageSegments = computed(() => {
  const usage = stats.value?.generationUsage
  if (!usage) return []
  return [
    { label: '已完成', value: usage.succeeded, color: '#168264' },
    { label: '处理中', value: usage.running, color: '#6ca9d4' },
    { label: '待确认', value: usage.unknown, color: '#ddb45d' },
    { label: '其他结果', value: Math.max(0, usage.requests - usage.succeeded - usage.running - usage.unknown), color: '#c6d2cc' },
  ]
})
const usageTotal = computed(() => usageSegments.value.reduce((total, segment) => total + segment.value, 0))
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
  try { stats.value = await fetchAdminStats(); updatedAt.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date()) }
  catch (e: unknown) { error.value = e instanceof Error ? e.message : '概览加载失败' }
  finally { loading.value = false }
}
onActivated(refresh)
</script>

<template>
  <section class="admin-section overview-page" aria-label="运行概览">
    <div class="overview-welcome">
      <div><div class="welcome-date"><UIcon name="i-lucide-calendar-days" class="size-3.5" />{{ dateLabel }}</div><h2>欢迎回来<span v-if="user">，{{ user.username }}</span></h2><p>资料、用户与服务动态，尽在掌握。</p></div>
      <div class="welcome-actions"><UButton icon="i-lucide-library" label="管理资料" @click="navigateAdmin('papers')" /><UButton icon="i-lucide-chart-no-axes-combined" label="内容数据" color="neutral" variant="outline" @click="navigateAdmin('miniAnalytics')" /></div>
      <UIcon name="i-lucide-notebook-pen" class="welcome-art" aria-hidden="true" />
    </div>
    <div class="section-toolbar"><h2>平台概况<span class="section-caption">运营数据，一目了然</span></h2><div class="actions-row"><span v-if="updatedAt" class="updated-time">更新于 {{ updatedAt }}</span><UTooltip text="刷新数据"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" size="sm" aria-label="刷新概览" :loading="loading" @click="refresh" /></UTooltip></div></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <div v-if="!stats && loading" class="overview-metrics" role="status" aria-label="正在加载概览"><USkeleton v-for="n in 4" :key="n" class="h-24 rounded-md" /></div>
    <dl v-if="stats" class="overview-metrics">
      <div class="metric-users"><dt><span class="metric-icon"><UIcon name="i-lucide-users-round" class="size-5" /></span>出题用户</dt><dd>{{ stats.users.toLocaleString() }}</dd><span>{{ stats.activeUsers }} 位启用中</span></div>
      <div class="metric-templates"><dt><span class="metric-icon"><UIcon name="i-lucide-files" class="size-5" /></span>用户模板</dt><dd>{{ stats.templates.toLocaleString() }}</dd><span>已保存模板</span></div>
      <div class="metric-feedback"><dt><span class="metric-icon"><UIcon name="i-lucide-message-square" class="size-5" /></span>用户反馈</dt><dd>{{ stats.feedbacks.toLocaleString() }}</dd><span>{{ stats.feedbacksOob }} 条超纲反馈</span></div>
      <div class="metric-generation"><dt><span class="metric-icon"><UIcon name="i-lucide-activity" class="size-5" /></span>生成请求</dt><dd>{{ stats.generationUsage?.requests.toLocaleString() ?? '—' }}</dd><span>最近 24 小时</span></div>
    </dl>
    <UAlert v-if="stats?.securityWarnings?.length" title="部署提醒" :description="stats.securityWarnings.join('；')" color="warning" variant="soft" class="notice" />
    <div class="overview-columns">
      <section class="overview-tasks" aria-label="待办事项">
        <div class="overview-section-heading"><h2><UIcon name="i-lucide-list-checks" class="size-4" />待办事项</h2><span>点击即可前往处理</span></div>
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
        <div class="overview-section-heading"><h2><UIcon name="i-lucide-cpu" class="size-4" />模型服务</h2><span>出题能力</span></div>
        <template v-if="stats">
          <div class="service-model"><span class="service-indicator" :class="{ configured: stats.llmConfigured }"></span><strong>{{ stats.server.model || '未配置模型' }}</strong><UBadge :color="stats.llmConfigured ? 'success' : 'warning'" variant="soft" size="sm">{{ stats.llmConfigured ? '已配置' : '待配置' }}</UBadge></div>
          <dl class="service-facts"><dt>密钥加密</dt><dd>{{ stats.server.encryption }}</dd><dt>服务版本</dt><dd>v{{ stats.server.version }}</dd><dt>管理员</dt><dd>{{ stats.admins }} 人</dd></dl>
        </template>
        <p v-else class="service-placeholder">{{ loading ? '正在读取模型配置…' : '暂未获取服务信息，请刷新概览重试。' }}</p>
        <UButton icon="i-lucide-settings-2" label="模型配置" color="neutral" variant="outline" size="sm" @click="$emit('configure')" />
      </section>
    </div>
    <section v-if="stats?.generationUsage" class="usage-section" aria-label="生成用量">
      <div class="overview-section-heading"><h2>生成用量</h2><span>最近 24 小时</span></div>
      <div class="usage-distribution" aria-label="生成请求状态分布">
        <div class="usage-summary"><span>请求处理情况</span><strong>{{ stats.generationUsage.requests.toLocaleString() }}<small> 次请求</small></strong></div>
        <div class="usage-track" aria-hidden="true"><span v-for="segment in usageSegments" v-show="segment.value > 0" :key="segment.label" :style="{ width: (usageTotal ? segment.value / usageTotal * 100 : 0) + '%', backgroundColor: segment.color }"></span></div>
        <ul class="usage-legend"><li v-for="segment in usageSegments" :key="segment.label"><i :style="{ backgroundColor: segment.color }"></i>{{ segment.label }}<strong>{{ segment.value }}</strong></li></ul>
      </div>
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
.overview-welcome { position:relative;isolation:isolate;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:28px 32px;margin-bottom:28px;background:#e5f1e9;border:1px solid #d6e7dc;border-radius:16px; }
.welcome-date { display:flex;align-items:center;gap:7px;font-size:11px;color:#527562; }
.overview-welcome h2 { font-size:23px;font-weight:650;color:#204e3d;margin:10px 0 6px;overflow-wrap:anywhere; }
.overview-welcome p { font-size:12px;color:#527562;margin:0; }
.welcome-actions { display:flex;flex-wrap:wrap;gap:10px;flex:none; }
.welcome-art { position:absolute;right:32px;bottom:-35px;width:175px;height:175px;color:#21674808;z-index:-1;transform:rotate(-18deg); }
.section-caption { font-weight:400;font-size:11px;color:var(--ui-text-muted);margin-left:12px; }
.updated-time { font-size:10px;color:var(--ui-text-muted); }
.overview-metrics { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0 0 24px; }
.overview-metrics > div { position:relative;padding:20px 22px;border:1px solid #e5ece9;border-radius:14px;min-width:0;background:#fff;box-shadow:var(--admin-shadow);transition:transform .2s,box-shadow .2s; }
.overview-metrics > div:hover { transform:translateY(-3px);box-shadow:0 8px 24px #183e3214; }
.overview-metrics dt { display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ui-text-toned); }
.metric-icon { display:grid;place-items:center;width:36px;height:36px;flex:none;border-radius:11px;background:#e8f5ee;color:#26785a; }
.metric-templates .metric-icon { background:#eaf2fa;color:#4a80ad; }
.metric-feedback .metric-icon { background:#fbf2df;color:#9d792b; }
.metric-generation .metric-icon { background:#eeedf8;color:#7b71a8; }
.overview-metrics dd { font-size:34px;font-weight:650;letter-spacing:-1px;line-height:1.3;margin:16px 0 4px;font-variant-numeric:tabular-nums;color:#243e34; }
.overview-metrics > div > span { color:var(--ui-text-muted);font-size:11px; }
.overview-columns { display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,1fr);gap:20px; }
.overview-tasks, .overview-service, .usage-section { padding:24px;background:#fff;border:1px solid #e5ece9;border-radius:14px;box-shadow:var(--admin-shadow); }
.overview-section-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px; }
.overview-section-heading h2 { display:flex;align-items:center;gap:8px;margin:0;font-size:14px;font-weight:600; }
.overview-section-heading h2 > span { color:#698778; }
.overview-section-heading > span { color:var(--ui-text-muted);font-size:11px; }
.task-row { border-bottom:1px solid var(--ui-border-muted); }
.task-row:last-child { border-bottom:0; }
.task-action { display:flex;align-items:center;gap:14px;width:100%;min-height:68px;padding:12px 8px;text-align:left;border-radius:9px; }
.task-action:hover { background:#f4f9f6; }
.task-action:hover .task-arrow { color:var(--ui-primary);transform:translate(2px,-2px); }
.task-icon { display:grid;place-items:center;width:38px;height:38px;flex:none;background:#eaf4ef;color:#087452;border-radius:11px; }
.task-icon-requests { background:#edf3fb;color:#3267aa; }
.task-icon-feedback { background:#f1f1f5;color:#606070; }
.task-icon-refunds { background:#fbf3e2;color:#987220; }
.task-label { flex:1;font-size:13px; }
.task-row strong { font-size:18px;font-weight:600;font-variant-numeric:tabular-nums;min-width:26px;text-align:right; }
.task-row strong.has-tasks { color:var(--ui-text-highlighted); }
.task-arrow { color:var(--ui-text-muted);margin-left:8px;transition:transform .2s,color .2s; }
.overview-service { min-width:0; }
.service-model { display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:18px 16px;background:#f3f8f5;border:1px solid #e4eee7;border-radius:10px; }
.service-model strong { font-size:14px;font-weight:600;overflow-wrap:anywhere; }
.service-indicator { width:7px;height:7px;border-radius:50%;background:var(--ui-warning);flex:none; }
.service-indicator.configured { background:var(--ui-primary); }
.service-facts { display:grid;grid-template-columns:90px minmax(0,1fr);gap:16px;margin:24px 0;font-size:12px; }
.service-placeholder { color:var(--ui-text-muted);font-size:12px;margin:30px 0; }
.service-facts dt { color:var(--ui-text-muted); }
.service-facts dd { margin:0;overflow-wrap:anywhere; }
.usage-section { margin-top:20px; }
.usage-distribution { padding:18px 20px;background:#f7faf8;border-radius:10px; }
.usage-summary { display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:var(--ui-text-muted); }
.usage-summary strong { color:#285542;font-size:18px;font-variant-numeric:tabular-nums; }
.usage-summary small { font-size:11px;font-weight:400;color:var(--ui-text-muted); }
.usage-track { display:flex;gap:3px;height:10px;background:#e7eeea;border-radius:6px;overflow:hidden;margin:14px 0; }
.usage-track > span { border-radius:3px;transition:width .5s ease; }
.usage-legend { display:flex;flex-wrap:wrap;gap:12px 24px;list-style:none;margin:0;padding:0;font-size:11px;color:var(--ui-text-muted); }
.usage-legend li { display:flex;align-items:center;gap:7px; }
.usage-legend i { width:7px;height:7px;border-radius:50%; }
.usage-legend strong { font-weight:550;color:var(--ui-text);font-variant-numeric:tabular-nums; }
.usage-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;margin:24px 0; }
.usage-grid dt { font-size:12px;color:var(--ui-text-muted); }
.usage-grid dd { margin:10px 0 0;font-size:24px;font-weight:550;font-variant-numeric:tabular-nums;overflow-wrap:anywhere; }
.usage-grid .token-count { font-size:20px; }
.usage-caption { display:flex;align-items:center;flex-wrap:wrap;gap:12px 20px;padding:14px 0 0;border-top:1px solid var(--ui-border-muted);color:var(--ui-text-muted);font-size:11px; }
@media(max-width:1150px) { .overview-metrics { gap:12px; }.overview-metrics > div { padding:18px 16px; }.overview-metrics dt { flex-direction:column;align-items:flex-start; }.overview-welcome { padding:24px; }.welcome-actions { flex-direction:column; } }
@media(max-width:1050px) { .overview-columns { grid-template-columns:1fr;gap:20px; }.service-facts { margin:20px 0; } }
@media(max-width:600px) {
  .overview-welcome { flex-direction:column;align-items:flex-start;padding:22px;gap:20px;margin-bottom:24px; }
  .overview-welcome h2 { font-size:20px; }.welcome-actions { flex-direction:row;gap:8px; }
  .section-caption { display:none; }
  .overview-metrics { grid-template-columns:repeat(2,minmax(0,1fr));gap:12px; }
  .overview-metrics > div { padding:16px; }
  .overview-metrics dd { font-size:28px; }.overview-metrics dt { gap:8px;flex-direction:row; }
  .metric-icon { width:28px;height:28px;border-radius:8px; }
  .overview-tasks, .overview-service, .usage-section { padding:18px; }
  .usage-grid { grid-template-columns:repeat(2,minmax(0,1fr));gap:24px 16px; }
  .usage-distribution { padding:14px; }.usage-legend { gap:10px 16px; }
  .task-action { gap:10px;padding:12px 0; }.task-icon { width:34px;height:34px; }
}
@media(max-width:360px) { .overview-metrics dt { flex-direction:column;align-items:flex-start; }.overview-section-heading { gap:8px; }.overview-section-heading > span { font-size:10px; } }
</style>
