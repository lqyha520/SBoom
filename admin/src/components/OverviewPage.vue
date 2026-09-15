<script setup lang="ts">
import { onActivated, ref } from 'vue'
import { fetchAdminStats, type AdminStats } from '../api'

defineEmits<{ configure: [] }>()
const stats = ref<AdminStats | null>(null)
const loading = ref(false)
const error = ref('')
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { stats.value = await fetchAdminStats() }
  catch (e: unknown) { error.value = e instanceof Error ? e.message : '概览加载失败' }
  finally { loading.value = false }
}
onActivated(load)
</script>

<template>
  <section class="admin-section" aria-label="运行概览">
    <div class="section-toolbar"><h2>平台数据</h2><UTooltip text="刷新数据"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" aria-label="刷新概览" :loading="loading" @click="load" /></UTooltip></div>
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
        <div class="usage-caption"><span>每用户请求上限 {{ stats.generationUsage.daily_limit }}</span><span>结果不确定 {{ stats.generationUsage.unknown }}</span><span>用量已上报 {{ stats.generationUsage.reported_calls }} 次</span></div>
      </section>
      <div class="service-info"><h2 class="section-title">服务信息</h2><dl class="info-list"><dt>服务版本</dt><dd>v{{ stats.server.version }}</dd><dt>当前模型</dt><dd>{{ stats.server.model }}</dd><dt>密钥加密</dt><dd>{{ stats.server.encryption }}</dd></dl></div>
    </template>
  </section>
</template>

<style scoped>
.usage-section { padding: 24px 0; border-bottom: 1px solid var(--ui-border); }
.usage-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; margin-top: 20px; }
.usage-grid dt { font-size: 12px; color: var(--ui-text-muted); }
.usage-grid dd { margin: 10px 0 0; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.usage-grid .token-count { font-size: 20px; }
.usage-caption { display: flex; flex-wrap: wrap; gap: 20px; margin-top: 18px; color: var(--ui-text-muted); font-size: 11px; }
@media (max-width: 760px) { .usage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
