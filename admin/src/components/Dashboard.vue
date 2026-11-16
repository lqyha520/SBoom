<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { lazyComponent } from '../../../shared/async-component'
import * as api from '../api'
import { adminRoute, navigateAdmin, listenAdminRoute, canLeaveAdmin } from '../navigation'
import { allowedAdminGroups, adminSidebarTab, isUserServiceTab, isXhsContentTab, searchAdminNavigation, userServiceTabs, xhsContentTabs } from '../admin-navigation'
import NavigationSearch from './NavigationSearch.vue'
import XhsContentNavigation from './XhsContentNavigation.vue'

import { canAdmin } from '../permissions'
const groups = computed(() => allowedAdminGroups())

const props = defineProps<{ user: api.UserInfo }>()
const emit = defineEmits<{ logout: [] }>()
const userServiceCenter = lazyComponent(() => import('./UserServiceCenter.vue'))
const financeCenter = lazyComponent(() => import('./FinanceCenter.vue'))
const views = {
  referralEarnings: financeCenter, referralRules: financeCenter,
  financeOverview: financeCenter, financeSettlements: financeCenter, financePayments: financeCenter,
  financeBills: financeCenter, financeExpenses: financeCenter, financeMonthly: financeCenter, financeSettings: financeCenter,
  financeLedger: lazyComponent(() => import('./FinanceLedger.vue')),
  accountSecurity: lazyComponent(() => import('./AccountSecurity.vue')),
  referrals: lazyComponent(() => import('./ReferralManager.vue')),
  settlements: lazyComponent(() => import('./SettlementManager.vue')),
  overview: lazyComponent(() => import('./OverviewPage.vue')),
  llm: lazyComponent(() => import('./ModelSettings.vue')),
  users: lazyComponent(() => import('./UsersPage.vue')),
  papers: lazyComponent(() => import('./PublicPapers.vue')),
  miniUsers: lazyComponent(() => import('./MiniUsers.vue')),
  adminAccounts: lazyComponent(() => import('./AdminAccounts.vue')),
  supportCenter: userServiceCenter,
  topics: lazyComponent(() => import('./TopicManager.vue')),
  catalogTags: lazyComponent(() => import('./CatalogTags.vue')),
  xhsResearch: lazyComponent(() => import('./XhsResearch.vue')),
  xhsIdeas: lazyComponent(() => import('./XhsIdeas.vue')),
  xhsMaterials: lazyComponent(() => import('./XhsMaterials.vue')),
  xhsDrafts: lazyComponent(() => import('./XhsDrafts.vue')),
  xhsPublishing: lazyComponent(() => import('./XhsPublishing.vue')),
  xhsAnalytics: lazyComponent(() => import('./XhsAnalytics.vue')),
  xhsAssets: lazyComponent(() => import('./XhsAssets.vue')),
  xhsAccounts: lazyComponent(() => import('./XhsAccounts.vue')),
  resourceRequests: userServiceCenter,
  accountClosures: lazyComponent(() => import('./AccountClosures.vue')),
  membershipPlans: lazyComponent(() => import('./MembershipPlans.vue')),
  membershipContact: lazyComponent(() => import('./MembershipContactSettings.vue')),
  membershipCards: lazyComponent(() => import('./MembershipCards.vue')),
  orders: lazyComponent(() => import('./OrderManager.vue')),
  reconciliations: lazyComponent(() => import('./Reconciliations.vue')),
  delivery: lazyComponent(() => import('./DeliveryStatus.vue')),
  miniAnalytics: lazyComponent(() => import('./MiniAnalytics.vue')),
  categories: lazyComponent(() => import('./CategoryManager.vue')),
  banners: lazyComponent(() => import('./BannerManager.vue')),
  notices: lazyComponent(() => import('./NoticeManager.vue')),
  documents: lazyComponent(() => import('./DocumentManager.vue')),
  dictionary: lazyComponent(() => import('./DictionaryManager.vue')),
  typeAccess: lazyComponent(() => import('./TypeAccessRules.vue')),
  feedback: userServiceCenter,
  logs: lazyComponent(() => import('./LogsPage.vue')),
}
type Tab = keyof typeof views
const navSearch = ref('')
const visibleGroups = computed(() => searchAdminNavigation(navSearch.value))
const favoriteKey = 'lc-admin-favorites:' + props.user.id
const favorites = ref<Tab[]>(readFavorites())
function readFavorites(): Tab[] {
  try { const value: unknown = JSON.parse(localStorage.getItem(favoriteKey) || 'null'); if (Array.isArray(value)) return [...new Set(value.filter((id): id is Tab => typeof id === 'string' && id in views).map(adminSidebarTab))].slice(0, 6) } catch { /* 不可用时使用默认入口 */ }
  return ['papers', 'resourceRequests', 'orders']
}
function toggleFavorite(id: Tab) {
  if (favorites.value.includes(id)) favorites.value = favorites.value.filter(value => value !== id)
  else if (favorites.value.length < 6) favorites.value.push(id)
  try { localStorage.setItem(favoriteKey, JSON.stringify(favorites.value)) } catch { /* 当前页面仍可使用 */ }
}
const favoriteItems = computed(() => favorites.value.flatMap(id => groups.value.flatMap(group => group.items).filter(item => item.id === id)))
const favoriteMenu = computed(() => favoriteItems.value.map(item => ({ label: item.label, icon: item.icon, onSelect: () => navigateAdmin(item.id) })))
const flat = computed(() => groups.value.flatMap(group => group.items))
const tab = computed<Tab>({ get: () => adminRoute.tab, set: value => navigateAdmin(value) })
const inContentWorkbench = computed(() => isXhsContentTab(tab.value))
const inUserServiceCenter = computed(() => isUserServiceTab(tab.value))
const serviceProps = computed(() => isUserServiceTab(tab.value) ? { active: tab.value } : tab.value.startsWith('finance') || tab.value.startsWith('referral') && tab.value !== 'referrals' ? { active: tab.value } : {})
const lastContentTab = ref<Tab>(inContentWorkbench.value ? tab.value : 'xhsResearch')
const lastServiceTab = ref<Tab>(inUserServiceCenter.value ? tab.value : 'resourceRequests')
const sidebarTab = computed<Tab>({
  get: () => adminSidebarTab(tab.value),
  set: value => navigateAdmin(isXhsContentTab(value) && canAdmin(lastContentTab.value) ? lastContentTab.value : isUserServiceTab(value) && canAdmin(lastServiceTab.value) ? lastServiceTab.value : value),
})
const main = ref<HTMLElement | null>(null)
let stopNavigation: (() => void) | undefined
onMounted(() => { stopNavigation = listenAdminRoute() })
onBeforeUnmount(() => stopNavigation?.())

// 每个浏览器保留分组状态，首次进入只展开当前业务组。
const NAV_STATE_KEY = 'lc-admin-nav-collapsed'
const collapsed = ref<string[]>(readCollapsed())
function readCollapsed(): string[] {
  try {
    const saved = localStorage.getItem(NAV_STATE_KEY)
    if (saved) {
      const parsed: unknown = JSON.parse(saved)
      if (Array.isArray(parsed)) return parsed.filter((id): id is string => typeof id === 'string' && groups.value.some(group => group.id === id) && !groups.value.find(group => group.id === id)?.items.some(item => item.id === sidebarTab.value))
    }
  } catch { return [] }
  return groups.value.filter(group => !group.items.some(item => item.id === sidebarTab.value)).map(group => group.id)
}
function persistCollapsed() {
  try { localStorage.setItem(NAV_STATE_KEY, JSON.stringify(collapsed.value)) } catch { /* 隐私模式下 localStorage 不可写，忽略即可 */ }
}
function isCollapsed(id: string) { return collapsed.value.includes(id) }
function toggleGroup(id: string) {
  collapsed.value = isCollapsed(id) ? collapsed.value.filter(value => value !== id) : [...collapsed.value, id]
  persistCollapsed()
}
// 切到某个菜单项时，它所在的组必须展开，否则用户会「跳到一个看不见当前项」的分组里
watch(tab, async value => {
  if (isXhsContentTab(value)) lastContentTab.value = value
  if (isUserServiceTab(value)) lastServiceTab.value = value
  const group = groups.value.find(item => item.items.some(entry => entry.id === adminSidebarTab(value)))
  if (group && isCollapsed(group.id)) { collapsed.value = collapsed.value.filter(id => id !== group.id); persistCollapsed() }
  await nextTick()
  main.value?.scrollTo?.({ top: 0, behavior: 'instant' })
  document.querySelector('.nav-item[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
})
const activeTab = computed(() => userServiceTabs.find(item => item.id === tab.value) || xhsContentTabs.find(item => item.id === tab.value) || flat.value.find(item => item.id === tab.value) || { label: '暂无授权菜单', icon: 'i-lucide-shield-x' })
const activeGroup = computed(() => groups.value.find(group => group.items.some(item => item.id === sidebarTab.value)) || { id: '', label: '管理后台' })
const descriptions: Partial<Record<Tab, string>> = {
  overview: '从这里开始，掌握平台动态与今日待办。',
  papers: '整理教学资料，让每一份好习题都被看见。',
  llm: '管理出题模型，随时核对配置与连接状态。',
  xhsAssets: '保存原创图片、视频和封面模板，记录来源并反复使用。',
  xhsAccounts: '每个账号使用独立浏览器，登录状态保存在这台电脑。',
  orders: '查看会员交易，跟进订单与退款处理。',
  referrals: '管理专属推广码，核对注册来源与付费归属。',
  settlements: '仅首次付费奖励，核对手续费、个人费用与税费后结款。',
  referralEarnings: '查看本人奖励、申请结算，跟进审核与付款进度。',
  referralRules: '维护推广奖励与处理目标，查看当前生效的奖励口径。',
  financeOverview: '集中处理核对、审核、付款与异常待办。',
  financeSettlements: '核对费用、审核结算，处理调整与结算异议。',
  financePayments: '集中处理待付款清单、付款批次与银行回单。',
  financeBills: '导入渠道账单，核对收退款及费用差异。',
  financeExpenses: '汇总各活动投入，核对成本与原始凭据。',
  financeMonthly: '核对推广人月度余额，下载对账单并确认留档。',
  financeSettings: '安排财务职责，设置独立审核与付款规则。',
  membershipContact: '维护小程序统一展示的会员权益说明与客服联系信息。',
}
const pageDescription = computed(() => descriptions[tab.value] || `集中管理${activeTab.value.label}，让日常工作更有条理。`)
const loggingOut = ref(false)
const logoutError = ref('')
async function logout() {
  if (loggingOut.value || !canLeaveAdmin()) return
  loggingOut.value = true
  logoutError.value = ''
  try { await api.logout(); emit('logout') }
  catch (error) { logoutError.value = error instanceof Error ? error.message : '退出失败，请重试' }
  finally { loggingOut.value = false }
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-header">
      <a class="brand" href="/"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div><div class="brand-name">管理控制台</div><div class="brand-caption">出题工作台 · 管理中心</div></div></a>
      <div class="header-location"><span>{{ inContentWorkbench ? '内容工作台' : inUserServiceCenter ? '用户服务中心' : activeGroup.label }}</span><UIcon name="i-lucide-chevron-right" class="size-3" /><strong>{{ activeTab.label }}</strong></div>
      <div class="admin-header-actions">
        <NavigationSearch :user-id="user.id" :favorites="favoriteItems" />
        <UDropdownMenu :items="favoriteMenu.length ? favoriteMenu : [{ label: '暂无常用入口', disabled: true }]">
          <UButton icon="i-lucide-star" aria-label="常用入口" color="neutral" variant="ghost" size="sm" class="header-favorites"><span class="header-favorites-label">常用入口</span></UButton>
        </UDropdownMenu>
        <UButton href="/" icon="i-lucide-arrow-up-right" label="出题工作台" color="neutral" variant="ghost" class="workbench-link" size="sm" />
        <UDropdownMenu :items="[{ label: '退出登录', icon: 'i-lucide-log-out', disabled: loggingOut, onSelect: logout }]">
          <UButton color="neutral" variant="ghost" :aria-label="'账号菜单：' + user.username">
            <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span><span class="admin-account">{{ user.username }}</span><UIcon name="i-lucide-chevron-down" class="size-3 text-muted" />
          </UButton>
        </UDropdownMenu>
      </div>
    </header>
    <div class="admin-workspace">
      <aside class="admin-sidebar">
        <div class="sidebar-intro"><span>工作空间</span><UIcon name="i-lucide-grid-2x2" class="size-3.5" /></div>
        <label class="mobile-nav">管理页面<select v-model="sidebarTab" aria-label="选择管理页面"><optgroup v-for="group in groups" :key="group.id" :label="group.label"><option v-for="item in group.items" :key="item.id" :value="item.id">{{ item.label }}</option></optgroup></select></label>
        <div class="nav-search"><UInput v-model="navSearch" icon="i-lucide-search" aria-label="搜索管理菜单" placeholder="搜索菜单" class="w-full" /><UButton v-if="navSearch" label="清除搜索" size="xs" variant="ghost" @click="navSearch = ''" /></div>
        <nav aria-label="管理后台导航">
          <p v-if="!visibleGroups.length" class="text-xs text-muted p-3">没有匹配菜单</p>
          <div v-for="group in visibleGroups" :key="group.id" class="nav-group">
            <button type="button" class="nav-group-caption" :class="{ 'active-group': activeGroup.id === group.id }" :aria-expanded="!!navSearch || !isCollapsed(group.id)" :aria-controls="'nav-panel-' + group.id" :title="(isCollapsed(group.id) ? '展开' : '折叠') + '「' + group.label + '」'" @click="toggleGroup(group.id)">
              <UIcon :name="group.icon" class="size-4" /><span>{{ group.label }}</span>
              <UIcon name="i-lucide-chevron-down" class="size-3 nav-group-chevron" :class="{ collapsed: !navSearch && isCollapsed(group.id) }" />
            </button>
            <Transition name="nav-group-reveal">
            <div v-show="navSearch || !isCollapsed(group.id)" :id="'nav-panel-' + group.id" class="nav-group-items" :inert="!navSearch && isCollapsed(group.id)">
              <div v-for="item in group.items" :key="item.id" class="nav-row"><button class="nav-item" :class="{ active: sidebarTab === item.id }" :aria-current="sidebarTab === item.id ? 'page' : undefined" @click="sidebarTab = item.id">
                <UIcon :name="item.icon" class="size-4 nav-item-icon" />
                <span>{{ item.label }}</span>
              </button><button class="nav-pin" :class="{ pinned: favorites.includes(item.id) }" :title="(favorites.includes(item.id) ? '移出常用：' : '加入常用：') + item.label" :aria-label="(favorites.includes(item.id) ? '移出常用：' : '加入常用：') + item.label" :aria-pressed="favorites.includes(item.id)" :disabled="!favorites.includes(item.id) && favorites.length >= 6" @click="toggleFavorite(item.id)"><UIcon name="i-lucide-star" class="size-3.5" /></button></div>
            </div>
            </Transition>
          </div>
        </nav>
        <div class="sidebar-footer"><span class="sidebar-status"></span><span>管理员工作区</span><UIcon name="i-lucide-shield-check" class="size-4" /></div>
      </aside>
      <main ref="main" class="admin-main">
        <UAlert v-if="logoutError" :title="logoutError" color="error" role="alert" />
        <XhsContentNavigation :user-id="user.id" v-if="inContentWorkbench" :active="tab" />
        <div v-else-if="!inUserServiceCenter && tab !== 'xhsAnalytics' && tab !== 'xhsAssets'" :key="tab" class="admin-page-heading"><div><div class="page-eyebrow"><span></span>{{ activeGroup.label }}</div><h1>{{ activeTab.label }}</h1><p>{{ pageDescription }}</p></div><span class="page-heading-icon" aria-hidden="true"><UIcon :name="activeTab.icon" class="size-7" /></span></div>
        <UAlert v-if="!canAdmin(tab)" title="暂无可访问的菜单" description="请联系超级管理员分配菜单及操作权限。" icon="i-lucide-shield-x" />
        <KeepAlive v-else :max="25"><component :is="views[tab]" :key="tab.startsWith('finance') || tab === 'referralEarnings' || tab === 'referralRules' ? tab : undefined" :user="props.user" v-bind="serviceProps" @configure="tab = 'llm'" /></KeepAlive>
      </main>
    </div>
  </div>
</template>

<style scoped>
.nav-search { padding:0 4px 20px; }
.nav-row { display:flex;align-items:center;min-width:0; }
.nav-row .nav-item { flex:1;min-width:0; }
.nav-row .nav-item span:last-child { overflow:hidden;text-overflow:ellipsis; }
.nav-item-icon { flex:none;opacity:.8; }
.nav-pin { flex:none;width:28px;height:32px;display:grid;place-items:center;border-radius:6px;color:#9dbab3;cursor:pointer;opacity:0;transition:opacity .18s,background .18s; }
.nav-row:hover .nav-pin, .nav-row:focus-within .nav-pin { opacity:1; }
.nav-pin:hover, .nav-pin:focus-visible, .nav-pin.pinned { color:#b6f0d8;background:#ffffff10; }
.nav-pin:disabled { opacity:0.3;cursor:default; }
.sidebar-status { width:6px;height:6px;border-radius:50%;background:var(--ui-primary); }
@media(max-width:1280px) { .header-favorites-label { display:none; } }
@media(max-width:800px) { .header-favorites { width:40px;min-height:40px;justify-content:center;padding:0; } }
@media(max-width:800px) { .nav-search, .sidebar-intro { display:none; } }

.mobile-nav { display:none }
@media (max-width: 800px) { .mobile-nav { display:flex; align-items:center; gap:12px; width:100%;font-size:12px;color:var(--ui-text-muted) } .mobile-nav select { flex:1; min-width:0; padding:8px; border:1px solid var(--ui-border); border-radius:6px; background:var(--ui-bg);color:var(--ui-text) } .admin-sidebar nav, .sidebar-footer { display:none !important } }
</style>
