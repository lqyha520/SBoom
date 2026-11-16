<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { useAdminListRoute } from '../navigation'
import { canPermission, permissionDirective as vPermission } from '../permissions'
import { dateTime, yuan, orderStatuses, type Order } from '../growth'
import { downloadPromotionCode, exportReferrals, referenceRewardLabel, promoters, promotionCode, referralAudit, referralOrders, referralSource, referralSummary, referralUsers, supplementReferral, type Promoter, type PromotionCode, type ReferralAudit, type ReferralSummary, type ReferralUser } from '../referrals'

import ReferralCampaigns from './ReferralCampaigns.vue'
import ReferralConversion from './ReferralConversion.vue'
import ReferralRules from './ReferralRules.vue'
import type { ConversionFilters } from '../referral-conversion'
import ReferralAcquisition from './ReferralAcquisition.vue'
import ReferralQuality from './ReferralQuality.vue'
import ReferralComparison from './ReferralComparison.vue'
import PromotionTabs from './PromotionTabs.vue'
import '../promotion-layout.css'

const props = defineProps<{ user: UserInfo }>()
const section = ref('')
const sections = [{ value: 'overview', label: '推广概览' }, { value: 'campaigns', label: '活动与推广码' }, { value: 'records', label: '用户与订单' }, { value: 'rules', label: '奖励规则' }]
const admin = ref('all'), start = ref(''), end = ref(''), q = ref(''), mode = ref('users'), pageNumber = ref(1), stage = ref('all'), asOf = ref('')
const conversionFilters = ref<ConversionFilters | null>(null)
const campaign = ref(''), dateBasis = ref<'created' | 'paid'>('paid')
const detail = ref(''), expenses = ref('')
const activeSection = computed(() => sections.some(item => item.value === section.value) ? section.value : mode.value === 'orders' || q.value ? 'records' : 'overview')
const accounts = ref<Promoter[]>([]), users = ref<ReferralUser[]>([]), orders = ref<Order[]>([]), total = ref(0)
const summary = ref<ReferralSummary>({ registrations: 0, orders: 0, paying_users: 0, paid_fen: 0, refunded_fen: 0, net_fen: 0 })
const code = ref<PromotionCode | null>(null), codeAdmin = ref(String(props.user.id)), version = ref('release')
const selected = ref<ReferralUser | null>(null), dialog = ref(false), targetAdmin = ref(''), reason = ref(''), history = ref<ReferralAudit[]>([])
const activeAdmins = computed(() => accounts.value.filter(item => item.is_active).map(item => ({ value: String(item.id), label: item.username })))
const filters = () => ({ admin_id: admin.value === 'all' ? undefined : admin.value, start_date: start.value, end_date: end.value, q: q.value.trim(), campaign_id: campaign.value, date_basis: dateBasis.value, stage: mode.value === 'users' && stage.value !== 'all' ? stage.value : undefined, as_of: mode.value === 'users' ? asOf.value : undefined })
const applied = ref<{ mode: string; filters: ReturnType<typeof filters> } | null>(null)
const updatedAt = ref(0)
const pendingFilters = computed(() => !!applied.value && (mode.value !== applied.value.mode || JSON.stringify(filters()) !== JSON.stringify(applied.value.filters)))
const hasFilters = computed(() => admin.value !== 'all' || start.value || end.value || campaign.value || q.value || stage.value !== 'all')
const page = useAdminPage(async valid => {
  const params = filters(), requestedMode = mode.value
  const [list, stats, people] = await Promise.all([
    mode.value === 'users' ? referralUsers(params, (pageNumber.value - 1) * 20) : referralOrders(params, (pageNumber.value - 1) * 20),
    referralSummary(params), promoters(),
  ])
  if (!valid()) return
  if (mode.value === 'users') users.value = list.items as ReferralUser[]
  else orders.value = list.items as Order[]
  total.value = list.total; summary.value = stats; accounts.value = people.items
  applied.value = { mode: requestedMode, filters: params }; updatedAt.value = Date.now() / 1000
  conversionFilters.value = { admin_id: params.admin_id, start_date: params.start_date, end_date: params.end_date, campaign_id: params.campaign_id }
  const last = Math.max(1, Math.ceil(total.value / 20))
  if (pageNumber.value > last) pageNumber.value = last
}, () => { dialog.value = false; code.value = null })
const { loading, busy, error, notice } = page
const route = useAdminListRoute('referrals', { section, admin, start, end, q, mode, campaign, basis: dateBasis, stage, asOf, page: pageNumber, detail, expenses }, page.load)
function search() {
  if (route.restoring) return
  if (start.value && end.value && start.value > end.value) { error.value = '起始日期不能晚于截止日期'; return }
  if (pageNumber.value !== 1) pageNumber.value = 1; else void page.load()
}
function resetFilters() { admin.value = 'all'; start.value = ''; end.value = ''; campaign.value = ''; q.value = ''; stage.value = 'all'; asOf.value = ''; search() }
watch([admin, mode], search)
function selectCampaign(id: string, owner: string) { section.value = 'records'; if (id) campaign.value = id; if (owner) admin.value = owner; search() }; watch(pageNumber, page.load)
function selectStage(value: string, at: number) { section.value = 'records'; mode.value = 'users'; stage.value = value; q.value = ''; asOf.value = String(at); search() }
watch(stage, search)
watch([start, end, admin, campaign], () => { if (!route.restoring) asOf.value = '' })
watch(codeAdmin, () => { code.value = null })
function getCode() { void page.act(async valid => { const value = await promotionCode(props.user.id, Number(codeAdmin.value)); if (valid()) code.value = value }) }
function downloadCode() { void page.act(async () => { await downloadPromotionCode(props.user.id, Number(codeAdmin.value), version.value) }) }
function copyCode() { void page.act(async valid => { if (code.value) { await navigator.clipboard.writeText(code.value.path); if (valid()) notice.value = '小程序推广路径已复制' } }) }
function download() {
  if (!applied.value || pendingFilters.value || loading.value) return
  const scope = applied.value
  void page.act(async () => { await exportReferrals(scope.mode === 'users' ? 'users' : 'orders', { ...scope.filters }) })
}
function open(item: ReferralUser) {
  void page.act(async valid => {
    const result = await referralAudit(item.id)
    if (!valid()) return
    selected.value = item; history.value = result.items; targetAdmin.value = ''; reason.value = ''; dialog.value = true
  })
}
function save() {
  if (!selected.value || !targetAdmin.value || reason.value.trim().length < 2) return
  const item = selected.value
  void page.act(async valid => {
    await supplementReferral(props.user.id, item.id, Number(targetAdmin.value), reason.value.trim())
    if (!valid()) return
    dialog.value = false; notice.value = '历史用户归属已补录，已有订单保持原归属'; await page.load()
  })
}
</script>

<template>
  <section class="admin-section promotion-workspace">
    <PromotionTabs :model-value="activeSection" id="referrals" label="推广页面导航" :items="sections" :disabled="busy || dialog" @update:model-value="section = $event" />
    <UAlert v-if="error" :title="error" color="error" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" class="notice" />
    <section v-show="activeSection === 'campaigns'" id="referrals-panel-campaigns" role="tabpanel" aria-labelledby="referrals-tab-campaigns" class="promotion-panel-stack">
    <div v-if="canPermission('referrals:create') || canPermission('referrals:export')" class="promotion-panel promotion-code field-stack">
      <h3 class="font-semibold">专属推广小程序码</h3>
      <div class="actions-row">
        <USelect v-if="user.is_super_admin" v-model="codeAdmin" :items="activeAdmins" aria-label="推广码所属管理员" :disabled="busy" />
        <UButton v-permission="'referrals:create'" label="获取推广码" icon="i-lucide-qr-code" size="md" :loading="busy" @click="getCode" />
        <USelect v-model="version" :items="[{ value: 'release', label: '正式版' }, { value: 'trial', label: '体验版' }, { value: 'develop', label: '开发版' }]" aria-label="小程序版本" :disabled="busy" />
        <UButton v-permission="'referrals:export'" label="下载小程序码" icon="i-lucide-download" size="md" variant="outline" :loading="busy" @click="downloadCode" />
      </div>
      <p v-if="code" class="text-sm break-all">{{ code.admin_name }}：{{ code.code }}<br>{{ code.path }} <UButton label="复制小程序路径" size="xs" variant="link" @click="copyCode" /></p>
      <p class="text-xs text-muted">正式推广前请先发布支持推广来源的小程序版本。体验版、开发版仅供有相应访问权限的微信账号验证。</p>
    </div>
    <div class="promotion-panel"><ReferralCampaigns :user="user" :accounts="accounts" :requested="detail" :requested-owner="admin" :requested-expenses="expenses === '1'" @close-detail="detail = ''; expenses = ''" @select="selectCampaign" /></div>
    </section>
    <section v-show="activeSection === 'rules'" id="referrals-panel-rules" role="tabpanel" aria-labelledby="referrals-tab-rules" class="promotion-panel promotion-settings"><ReferralRules expanded /></section>
    <section v-show="activeSection === 'overview' || activeSection === 'records'" :id="`referrals-panel-${activeSection === 'records' ? 'records' : 'overview'}`" role="tabpanel" :aria-labelledby="`referrals-tab-${activeSection === 'records' ? 'records' : 'overview'}`" class="promotion-panel">
    <div class="promotion-heading"><div><h2>{{ activeSection === 'overview' ? '推广表现' : '用户与订单明细' }}</h2><p>{{ activeSection === 'overview' ? '看清用户从哪里来，在哪一步完成付费。' : '查看推广归属、订单记录和奖励去向。' }}{{ user.is_super_admin ? '' : '仅展示归属到你的数据。' }}</p></div><UButton v-if="activeSection === 'overview'" label="管理推广活动" icon="i-lucide-plus" size="md" variant="soft" @click="section = 'campaigns'" /></div>
    <form class="promotion-filter" aria-label="推广数据筛选" @submit.prevent="search">
      <USelect v-if="user.is_super_admin" v-model="admin" size="md" :items="[{ value: 'all', label: '全部归属' }, { value: '0', label: '无归属管理员' }, ...accounts.map(item => ({ value: String(item.id), label: item.username + (item.is_active ? '' : '（已停用）') }))]" aria-label="归属管理员" :disabled="loading" />
      <UFormField label="起始日期"><UInput v-model="start" type="date" :max="end || undefined" size="md" :disabled="loading" /></UFormField>
      <UFormField label="截止日期"><UInput v-model="end" type="date" :min="start || undefined" size="md" :disabled="loading" /></UFormField>
      <UButton label="查询推广数据" icon="i-lucide-search" size="md" type="submit" :loading="loading" /><UButton v-if="hasFilters" label="重置筛选" icon="i-lucide-rotate-ccw" color="neutral" size="md" variant="ghost" :disabled="loading" @click="resetFilters" />
    </form>
    <UAlert v-if="pendingFilters" title="筛选已修改，请查询后再导出；当前结果仍按上次查询范围展示" color="info" class="mb-3" />
    <p v-if="applied" class="text-xs text-muted mb-3">结果日期：{{ applied.filters.start_date || '不限起始' }} 至 {{ applied.filters.end_date || '不限截止' }} · 关键词：{{ applied.filters.q || '全部' }} · 上次读取 {{ dateTime(updatedAt) }}</p>
    <p v-if="campaign" class="text-sm mb-3">已筛选推广活动 <UButton label="清除活动筛选" variant="link" @click="campaign = ''; search()" /></p>
    <div v-show="activeSection === 'overview'">
      <ReferralConversion v-if="conversionFilters" :filters="conversionFilters" @select="selectCampaign" @stage="selectStage" />
      <ReferralAcquisition v-if="conversionFilters" :filters="conversionFilters" />
      <ReferralQuality v-if="conversionFilters" :filters="conversionFilters" />
      <ReferralComparison v-if="conversionFilters" :filters="conversionFilters" @select="selectCampaign" />
      <div class="promotion-secondary mb-5"><h3 class="font-semibold">期间收入与奖励支出</h3><USelect v-model="dateBasis" :items="[{ value: 'paid', label: '按实际付款 / 退款日期' }, { value: 'created', label: '按订单创建日期' }]" aria-label="推广统计日期口径" :disabled="loading" @update:model-value="search" /></div>
      <p v-if="q" class="text-sm text-muted mb-4">收入已按明细关键词“{{ q }}”筛选 <UButton label="清除关键词" variant="link" @click="q = ''; search()" /></p>
      <dl class="promotion-metrics">
        <div><dt>收款减退款</dt><dd>{{ yuan(summary.net_fen) }}</dd><small>收款 {{ yuan(summary.paid_fen) }} · 退款 {{ yuan(summary.refunded_fen) }}</small></div>
        <div><dt>首次付费收入</dt><dd>{{ yuan(summary.first_paid_fen ?? 0) }}</dd><small>仅首次成功付款计奖励</small></div>
        <div><dt>续费收入</dt><dd>{{ yuan(summary.renewal_paid_fen ?? 0) }}</dd><small>续费不计首付奖励</small></div>
        <div><dt>参考税前奖励</dt><dd>{{ referenceRewardLabel(summary) }}</dd><small>{{ summary.reward_unknown ? '另有 ' + summary.reward_unknown + ' 笔费用待核对' : '包含待核定奖励，以结算为准' }}</small></div>
      </dl>
      <details class="text-xs text-muted mt-5"><summary class="cursor-pointer">收入统计口径</summary><p class="mt-3">日期按北京时间计算。{{ dateBasis === 'paid' ? '收入按实际付款日期、退款按完成日期' : '订单收入及退款按原订单创建日期归集' }}。明细关键词和活动筛选同步生效；收款减退款未扣渠道费和其他成本。</p></details>
    </div>
    <div v-show="activeSection === 'records'">
    <form class="promotion-record-toolbar" @submit.prevent="search">
      <USelect v-model="mode" size="md" :items="[{ value: 'users', label: '推广用户' }, { value: 'orders', label: '推广订单' }]" aria-label="明细类型" :disabled="loading" />
      <USelect v-if="mode === 'users'" v-model="stage" size="md" :items="[{ value: 'all', label: '全部注册用户' }, { value: 'not_ordered', label: '尚未下单' }, { value: 'unpaid', label: '下单未付' }, { value: 'paid', label: '曾付费' }, { value: 'ordered', label: '曾下单' }]" aria-label="转化阶段" :disabled="loading" />
      <UInput v-model="q" icon="i-lucide-search" size="md" :placeholder="mode === 'users' ? '账号或昵称' : '订单号、账号或昵称'" aria-label="搜索推广明细" maxlength="120" :disabled="loading" />
      <UButton label="搜索明细" size="md" type="submit" :loading="loading" />
      <UButton v-permission="'referrals:export'" label="导出 CSV" icon="i-lucide-download" color="neutral" size="md" variant="outline" :disabled="loading || busy || !total || !applied || pendingFilters" @click="download" />
    </form>
    <p v-if="mode === 'users' && asOf" class="text-xs text-muted mb-3">名单统计截至 {{ dateTime(Number(asOf)) }}，与所点击漏斗一致。<UButton label="查看最新进度" variant="link" @click="asOf = ''; search()" /></p><div class="data-scroll" :aria-busy="loading"><table class="data-table"><thead><tr><th>{{ mode === 'users' ? '用户' : '订单 / 用户' }}</th><th>来源 / 直接邀请人</th><th>归属管理员</th><th>{{ mode === 'users' ? '注册时间' : '金额 / 状态 / 创建时间' }}</th><th v-if="user.is_super_admin && mode === 'users'">历史来源</th></tr></thead>
      <tbody v-if="mode === 'users'"><tr v-for="item in users" :key="item.id"><td>{{ item.nickname || item.username }}<div class="text-xs text-muted">{{ item.username }}</div></td><td>{{ referralSource(item.referral) }}<div class="text-xs text-muted">{{ item.referral.inviter_name || '—' }}<p v-if="item.referral.campaign_name">{{ item.referral.campaign_name }} · {{ item.referral.campaign_source }}</p></div></td><td>{{ item.referral.admin_name || '无' }}</td><td>{{ dateTime(item.created_at) }}<p class="text-sm font-medium mt-1">{{ ({ paid: '曾付费', unpaid: '下单未付', not_ordered: '尚未下单' } as Record<string, string>)[item.stage || ''] || '—' }}</p><p v-if="item.last_order_at" class="text-xs text-muted">最近下单 {{ dateTime(item.last_order_at) }}</p><p v-if="item.last_paid_at" class="text-xs text-muted">最近付费 {{ dateTime(item.last_paid_at) }}</p></td><td v-if="user.is_super_admin"><UButton :label="item.referral.source === 'legacy' ? '补录归属' : '补录记录'" variant="link" :disabled="busy" @click="open(item)" /></td></tr></tbody>
      <tbody v-else><tr v-for="item in orders" :key="item.id"><td>{{ item.plan_name }} · {{ item.nickname || item.username }}<div class="text-xs text-muted">{{ item.id }}</div></td><td>{{ referralSource(item.referral) }}<div class="text-xs text-muted">{{ item.referral?.inviter_name || '—' }}<p v-if="item.referral?.campaign_name">{{ item.referral.campaign_name }} · {{ item.referral.campaign_source }}</p></div></td><td>{{ item.referral?.admin_name || '无' }}</td><td>{{ yuan(item.amount_fen) }} · {{ orderStatuses[item.status] }}<div class="text-xs text-muted">{{ dateTime(item.created_at) }}</div><a v-if="canPermission('settlements:view')" :href="'#settlements?mode=rewards&q=' + encodeURIComponent(item.id)" class="text-primary text-sm">查看该订单奖励与结算</a></td></tr></tbody>
    </table></div>
    <div v-if="!loading && !total" class="promotion-empty"><UIcon name="i-lucide-search-x" class="promotion-empty-icon" aria-hidden="true" /><strong>当前筛选范围内暂无记录</strong><p>{{ hasFilters ? '试试其他关键词，或重置筛选查看全部记录。' : '分享推广码后，可在这里查看带来的用户与订单。' }}</p><UButton v-if="hasFilters" label="查看全部记录" variant="outline" size="md" @click="resetFilters" /></div>
    <div class="table-footer"><span>共 {{ total }} 条 · 注册来源首次绑定后固定，订单保留下单时归属。</span><UPagination v-model:page="pageNumber" :total="total" :items-per-page="20" :disabled="loading" /></div>
    </div>
    </section>
    <UModal v-model:open="dialog" title="历史来源补录与记录" :dismissible="!busy"><template #body><div v-if="selected" class="field-stack">
      <p>{{ selected.nickname || selected.username }} · {{ selected.username }}</p>
      <form v-if="selected.referral.source === 'legacy'" class="field-stack" @submit.prevent="save">
        <UAlert title="仅影响此用户今后的新订单和分享归属，已有订单及已注册的受邀用户保持原归属" color="warning" />
        <UFormField label="归属管理员" required><USelect v-model="targetAdmin" :items="activeAdmins" :disabled="busy" class="w-full" /></UFormField>
        <UFormField label="补录原因" required><UTextarea v-model="reason" :disabled="busy" minlength="2" maxlength="500" required class="w-full" /></UFormField>
        <UButton label="确认补录" type="submit" :disabled="busy || !targetAdmin || reason.trim().length < 2" :loading="busy" />
      </form>
      <p v-if="!history.length" class="text-sm text-muted">暂无人工补录记录</p>
      <div v-for="item in history" :key="item.id" class="text-sm"><p>{{ dateTime(item.created_at) }} · {{ item.actor_name || '已删除管理员' }} → {{ item.after_json.admin_name }}</p><p class="whitespace-pre-wrap">{{ item.reason }}</p></div>
    </div></template></UModal>
  </section>
</template>
