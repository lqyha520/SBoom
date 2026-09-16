<script setup lang="ts">
import { ref } from 'vue'
import { useAdminPage } from '../admin-page'
import { getDelivery } from '../growth'
const data = ref<Awaited<ReturnType<typeof getDelivery>> | null>(null)
const labels: Record<string, string> = { pending: '等待发送', sending: '发送中', sent: '发送成功', failed: '平台拒绝', unknown: '结果未确认', skipped: '未发送' }
const page = useAdminPage(async valid => { const result = await getDelivery(); if (valid()) data.value = result })
const { error, loading } = page
</script>
<template><section class="admin-section"><div class="section-toolbar"><p class="text-sm text-muted">站内消息始终可用。用户在小程序主动订阅后，才会发送微信服务提醒。</p><UButton label="刷新状态" :loading="loading" variant="outline" @click="page.load" /></div><UAlert v-if="error" :title="error" color="error" class="notice" /><template v-if="data"><UAlert :title="data.available ? '微信订阅提醒已配置' : '微信订阅提醒未配置，使用站内消息'" :color="data.available ? 'success' : 'info'" class="notice" /><dl class="info-list"><dt>订阅模板</dt><dd>{{ data.template_id || '未配置' }}</dd></dl><div class="delivery-counts"><div v-for="(label, key) in labels" :key="key" class="metric"><div class="metric-label">{{ label }}</div><div class="metric-number">{{ data.delivery_counts[key] || 0 }}</div></div></div><p class="text-sm text-muted">“结果未确认”表示网络中断或发送超时，为避免重复提醒不会自动重发。完整处理结果仍保留在用户的消息中心。</p></template><div class="settings-section mt-6"><h3 class="section-title">配置方式</h3><p class="text-sm text-muted mt-3">在微信后台申请合适的服务通知模板，将模板 ID 和标题、正文、时间对应的字段名配置到服务端环境；重启正式服务后生效。</p><dl class="info-list"><dt>模板 ID</dt><dd><code>WECHAT_SUBSCRIBE_TEMPLATE_ID</code></dd><dt>标题字段</dt><dd><code>WECHAT_SUBSCRIBE_TITLE_FIELD</code> · thing 或 phrase 类型</dd><dt>正文字段</dt><dd><code>WECHAT_SUBSCRIBE_BODY_FIELD</code> · thing 类型</dd><dt>时间字段</dt><dd><code>WECHAT_SUBSCRIBE_TIME_FIELD</code> · time 或 date 类型</dd></dl></div></section></template>
<style scoped>.delivery-counts { display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:24px 0; }</style>
