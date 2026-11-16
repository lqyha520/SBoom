<script setup lang="ts">
import { computed, ref } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { canAdmin } from '../permissions'
import { navigateAdmin, type AdminTab } from '../navigation'
import { adminGroups } from '../admin-navigation'
import { dateTime } from '../growth'
import { settlementSummary, type SettlementSummary, type SettlementTiming } from '../settlement-operations'
import { disputes, financeGrant, financeUser } from '../promotion-finance'
import { settlementList, type SettlementKind } from '../settlements'
import SettlementOverview from './SettlementOverview.vue'
import FinanceCloseChecklist from './FinanceCloseChecklist.vue'
import SettlementNotices from './SettlementNotices.vue'
const props = defineProps<{ user: UserInfo }>()
const summary = ref<SettlementSummary | null>(null), unresolved = ref<number | null>(null), awaitingReview = ref<number | null>(null)
const updatedAt = ref(0)
const duties = computed(() => [
  { stage: 'Costs' as const, title: '费用核对', text: '从待对账申请开始，核对订单费用与凭据，再生成结算单。', target: 'financeSettlements' as const, values: { mode: 'requests', status: 'pending' } },
  { stage: 'Review' as const, title: '结算审核', text: '先处理未结束异议，再核定个人费用与税款，批准结算单。', target: 'financeSettlements' as const, values: { mode: 'statements', status: 'draft' } },
  { stage: 'Payout' as const, title: '付款登记', text: '整理已批准的结算单，完成实际转账后核对并登记回单。', target: 'financePayments' as const, values: {} as Record<string, string> },
].filter(item => financeGrant(props.user, item.stage, 'view')))
const links = computed(() => adminGroups.find(item => item.id === 'finance')!.items.filter(item => item.id !== 'financeOverview' && canAdmin(item.id)))
const page = useAdminPage(async valid => {
  if (!financeUser(props.user)) return
  const results = await Promise.allSettled([settlementSummary({}), Promise.all([disputes('open', 1), disputes('processing', 1)]), settlementList('statements', 0, { status: 'draft' })])
  if (!valid()) return
  const [totals, issues, review] = results
  summary.value = totals.status === 'fulfilled' ? totals.value : null
  unresolved.value = issues.status === 'fulfilled' ? issues.value.reduce((n, item) => n + item.total, 0) : null
  awaitingReview.value = review.status === 'fulfilled' ? review.value.total : null
  if (results.some(item => item.status === 'fulfilled')) updatedAt.value = Date.now() / 1000
  if (results.some(item => item.status === 'rejected')) page.error.value = '部分财务待办读取失败，可刷新或进入对应页面查看。'
})
function select(mode: SettlementKind, status: string, q = '') { navigateAdmin('financeSettlements', { mode, status, q }) }
function timing(value: SettlementTiming) { navigateAdmin('financeSettlements', { mode: 'requests', timing: value }) }
function go(id: AdminTab) { navigateAdmin(id) }
</script>
<template>
  <section class="admin-section promotion-workspace">
    <div v-if="financeUser(user)" class="promotion-panel">
      <div class="promotion-heading"><div><h2>财务待办</h2><p>按核对、审核、付款流程处理，点击状态进入对应记录。</p></div><UButton label="刷新财务待办" icon="i-lucide-refresh-cw" variant="outline" :loading="page.loading.value" @click="page.load" /></div>
      <UAlert v-if="page.error.value" :title="page.error.value" color="warning" class="mb-4" />
      <p v-if="updatedAt" class="text-xs text-muted mb-4" role="status">上次读取：{{ dateTime(updatedAt) }} · 刷新后查看最新处理状态</p>
      <p v-if="page.loading.value && !summary" role="status" class="promotion-loading">正在读取财务待办…</p>
      <SettlementOverview v-if="summary" :summary="summary" :disabled="page.loading.value" @select="select" @timing="timing" />
      <div v-if="financeUser(user)" class="finance-alerts"><button type="button" :disabled="awaitingReview === null || page.loading.value" @click="select('statements', 'draft')"><UIcon name="i-lucide-clipboard-check" /><span>待审核结算单</span><strong>{{ awaitingReview ?? '—' }} 份</strong></button><button type="button" :disabled="unresolved === null || page.loading.value" @click="navigateAdmin('financeSettlements', { section: 'disputes' })"><UIcon name="i-lucide-messages-square" /><span>未结束的结算异议</span><strong>{{ unresolved ?? '—' }} 条</strong></button><button v-if="summary" type="button" :disabled="page.loading.value" @click="select('rewards', 'exception')"><UIcon name="i-lucide-circle-alert" /><span>异常奖励待核对</span><strong>{{ summary.exception.count }} 笔</strong></button></div>
    </div>
    <FinanceCloseChecklist />
    <div v-if="duties.length" class="promotion-panel"><div class="promotion-heading"><div><h2>我的财务职责</h2><p>按你的授权说明下一步，独立复核规则仍由服务端校验。</p></div></div><div class="finance-entry-grid"><article v-for="item in duties" :key="item.stage" class="finance-duty-card"><h3>{{ item.title }} <span>{{ financeGrant(user, item.stage) ? '可办理' : '只读查看' }}</span></h3><p>{{ item.text }}</p><UButton :label="financeGrant(user, item.stage) ? '进入' + item.title : '查看' + item.title" variant="link" @click="navigateAdmin(item.target, item.values)" /></article></div></div>
    <div class="promotion-panel"><div class="promotion-heading"><div><h2>财务办理入口</h2><p>各页面按已授予的职责开放，结算与推广共用原始记录。</p></div></div><div class="finance-entry-grid"><button v-for="item in links" :key="item.id" type="button" class="promotion-list-card" @click="go(item.id)"><UIcon :name="item.icon" /><strong>{{ item.label }}</strong><span>进入办理 <UIcon name="i-lucide-arrow-up-right" /></span></button></div></div>
    <div v-if="financeUser(user)" class="promotion-panel"><h2 class="font-semibold mb-4">财务处理消息</h2><SettlementNotices :actor="user.id" @select="(mode, q) => select(mode, '', q)" @dispute="id => navigateAdmin('financeSettlements', { section: 'disputes', dispute: id })" /></div>
  </section>
</template>
