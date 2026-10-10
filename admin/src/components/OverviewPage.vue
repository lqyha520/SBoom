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
  <section class="admin-section" aria-label="运行概览">
    <div class="section-toolbar"><h2>待办事项</h2><UTooltip text="刷新数据"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" aria-label="刷新概览" :loading="loading" @click="refresh" /></UTooltip></div>
    <div class="task-grid">
      <article v-for="task in tasks" :key="task.id" class="task-card" :aria-busy="task.loading">
        <button type="button" @click="openTask(task.id)"><span>{{ task.label }}</span><strong>{{ task.loading && task.count === null ? '…' : task.error ? '—' : task.count }}</strong><span class="task-link">前往处理 →</span></button>
        <UButton v-if="task.error" :label="task.error + '，重试'" variant="link" size="xs" @click="loadTask(task.id)" />
      </article>
    </div>
    <h2 class="section-title mt-6 mb-3">平台数据</h2>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <div v-if="!stats && loading" class="metric-grid" role="status" aria-label="正在加载概览"><USkeleton v-for="n in 4" :key="n" class="h-36 rounded-lg" /></div>
    <template v-if="stats">
      <UAlert v-if="stats.securityWarnings?.length" title="部署提醒" :description="stats.securityWarnings.join('；')" color="warning" variant="soft" class="notice" />
      <div class="metric-grid">
        <article class="metric"><div class="metric-label">出题用户<UIcon name="i-lucide-users-round" class="size-4 text-primary" /></div><div class="metric-number">{{ stats.users }}</div><div class="metric-detail">{{ stats.activeUsers }} 启用 · {{ stats.admins }} 管理员</div></article>
        <article class="metric"><div class="metric-label">用户模板<UIcon name="i-lucide-files" class="size-4 text-secondary" /></div><div class="metric-number">{{ stats.templates }}</div><div class="metric-detail">已保存模板</div></article>
        <article class="metric"><div class="metric-label">用户反馈<UIcon name="i-lucide-message-square-text" class="size-4 text-secondary" /></div><div class="metric-number">{{ stats.feedbacks }}</div><div class="metric-detail">{{ stats.feedbacksOob }} 条超纲反馈</div></article>
        <article class="metric"><div class="metric-label">模型服务<UIcon name="i-lucide-cpu" class="size-4" :class="stats.llmConfigured ? 'text-primary' : 'text-warning'" /></div><div class="my-5"><UBadge :color="stats.llmConfigured ? 'success' : 'warning'" variant="subtle" size="lg">{{ stats.llmConfigured ? '已配置' : '待配置' }}</UBadge></div><UButton label="模型配置" variant="link" trailing-icon="i-lucide-arrow-right" size="xs" class="p-0" @click="$emit('configure')" /></article>
      </div>
      <section v-if="stats.generationUsage" class="usage-section" aria-label="生成用量">
        <h2 class="section-title">最近 24 小时</h2>
        <dl class="usage-grid">
          <div><dt>生成与校验请求</dt><dd>{{ stats.generationUsage.requests }}</dd></div>
          <div><dt>完成 / 处理中</dt><dd>{{ stats.generationUsage.succeeded }} / {{ stats.generationUsage.running }}</dd></div>
          <div><dt>模型尝试次数</dt><dd>{{ stats.generationUsage.model_calls }}</dd></div>
          <div><dt>已上报输入 / 输出 Token</dt><dd class="token-count">{{ stats.generationUsage.reported_calls ? stats.generationUsage.prompt_tokens.toLocaleString() + ' / ' + stats.generationUsage.completion_tokens.toLocaleString() : '未上报' }}</dd></div>
        </dl>
        <div class="usage-caption"><span>{{ stats.generationUsage.daily_limit > 0 ? '每用户 24 小时请求上限 ' + stats.generationUsage.daily_limit + ' 次' : '每用户每日请求次数不限' }}</span><span>结果不确定 {{ stats.generationUsage.unknown }}</span><span>用量已上报 {{ stats.generationUsage.reported_calls }} 次</span></div>
      </section>
      <div class="service-info"><h2 class="section-title">服务信息</h2><dl class="info-list"><dt>服务版本</dt><dd>v{{ stats.server.version }}</dd><dt>当前模型</dt><dd>{{ stats.server.model }}</dd><dt>密钥加密</dt><dd>{{ stats.server.encryption }}</dd></dl></div>
    </template>
  </section>
</template>

<style scoped>
.task-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px; }
.task-card { border:1px solid var(--ui-border);border-radius:10px;background:var(--ui-bg);overflow:hidden; }
.task-card button { display:flex;flex-direction:column;align-items:flex-start;width:100%;padding:16px;gap:8px;text-align:left;cursor:pointer; }
.task-card button:hover { background:var(--ui-bg-muted); }
.task-card strong { font-size:28px;font-variant-numeric:tabular-nums; }
.task-card span { font-size:13px; }
.task-link { color:var(--ui-primary); }
@media(max-width:760px) { .task-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
.usage-section { padding: 24px 0; border-bottom: 1px solid var(--ui-border); animation: fade-in 0.4s ease; }
.usage-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; margin-top: 20px; }
.usage-grid dt { font-size: 12px; color: var(--ui-text-muted); }
.usage-grid dd { margin: 10px 0 0; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; transition: color 0.2s ease; }
.usage-grid dd:hover { color: var(--ui-primary); }
.usage-grid .token-count { font-size: 20px; }
.usage-caption { display: flex; flex-wrap: wrap; gap: 20px; margin-top: 18px; color: var(--ui-text-muted); font-size: 11px; }
@media (max-width: 760px) { .usage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
