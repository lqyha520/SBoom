<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { lazyComponent } from '../../../shared/async-component'
import * as api from '../api'
import { adminRoute, navigateAdmin, listenAdminRoute, canLeaveAdmin } from '../navigation'
import { adminGroups as groups, searchAdminNavigation } from '../admin-navigation'

const props = defineProps<{ user: api.UserInfo }>()
const emit = defineEmits<{ logout: [] }>()
const views = {
  overview: lazyComponent(() => import('./OverviewPage.vue')),
  llm: lazyComponent(() => import('./ModelSettings.vue')),
  users: lazyComponent(() => import('./UsersPage.vue')),
  papers: lazyComponent(() => import('./PublicPapers.vue')),
  miniUsers: lazyComponent(() => import('./MiniUsers.vue')),
  adminAccounts: lazyComponent(() => import('./AdminAccounts.vue')),
  supportCenter: lazyComponent(() => import('./SupportCenter.vue')),
  topics: lazyComponent(() => import('./TopicManager.vue')),
  catalogTags: lazyComponent(() => import('./CatalogTags.vue')),
  resourceRequests: lazyComponent(() => import('./ResourceRequests.vue')),
  accountClosures: lazyComponent(() => import('./AccountClosures.vue')),
  membershipPlans: lazyComponent(() => import('./MembershipPlans.vue')),
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
  feedback: lazyComponent(() => import('./FeedbackPage.vue')),
  logs: lazyComponent(() => import('./LogsPage.vue')),
}
type Tab = keyof typeof views
const navSearch = ref('')
const visibleGroups = computed(() => searchAdminNavigation(navSearch.value))
const favoriteKey = 'lc-admin-favorites:' + props.user.id
const favorites = ref<Tab[]>(readFavorites())
function readFavorites(): Tab[] {
  try { const value: unknown = JSON.parse(localStorage.getItem(favoriteKey) || 'null'); if (Array.isArray(value)) return value.filter((id): id is Tab => typeof id === 'string' && id in views).slice(0, 6) } catch { /* 不可用时使用默认入口 */ }
  return ['papers', 'resourceRequests', 'orders']
}
function toggleFavorite(id: Tab) {
  if (favorites.value.includes(id)) favorites.value = favorites.value.filter(value => value !== id)
  else if (favorites.value.length < 6) favorites.value.push(id)
  try { localStorage.setItem(favoriteKey, JSON.stringify(favorites.value)) } catch { /* 当前页面仍可使用 */ }
}
const favoriteItems = computed(() => favorites.value.flatMap(id => groups.flatMap(group => group.items).filter(item => item.id === id)))
const flat = computed(() => groups.flatMap(group => group.items))
const tab = computed<Tab>({ get: () => adminRoute.tab, set: value => navigateAdmin(value) })
let stopNavigation: (() => void) | undefined
onMounted(() => { stopNavigation = listenAdminRoute() })
onBeforeUnmount(() => stopNavigation?.())

// ─── 一级菜单折叠 ───
// 折叠状态只影响当前浏览器，存 localStorage；移动端导航会拍平成横向图标条，
// 由样式强制展开（见 styles.css），所以这里的折叠不影响小屏。
const NAV_STATE_KEY = 'lc-admin-nav-collapsed'
const collapsed = ref<string[]>(readCollapsed())
function readCollapsed(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(NAV_STATE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string' && groups.some(group => group.id === id)) : []
  } catch { return [] }
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
  const group = groups.find(item => item.items.some(entry => entry.id === value))
  if (group && isCollapsed(group.id)) { collapsed.value = collapsed.value.filter(id => id !== group.id); persistCollapsed() }
  await nextTick()
  document.querySelector('.nav-item[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
})
const activeTab = computed(() => flat.value.find(item => item.id === tab.value)!)
const activeGroup = computed(() => groups.find(group => group.items.some(item => item.id === tab.value))!)
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
      <a class="brand" href="/"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div class="brand-name">管理控制台</div></a>
      <div class="admin-header-actions">
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
        <label class="mobile-nav">管理页面<select v-model="tab" aria-label="选择管理页面"><optgroup v-for="group in groups" :key="group.id" :label="group.label"><option v-for="item in group.items" :key="item.id" :value="item.id">{{ item.label }}</option></optgroup></select></label>
        <div class="nav-search"><UInput v-model="navSearch" icon="i-lucide-search" aria-label="搜索管理菜单" placeholder="搜索菜单" class="w-full" /><UButton v-if="navSearch" label="清除搜索" size="xs" variant="ghost" @click="navSearch = ''" /></div>
        <nav aria-label="管理后台导航">
          <div v-if="!navSearch && favoriteItems.length" class="nav-group favorite-nav"><span class="nav-group-caption">常用入口</span><button v-for="item in favoriteItems" :key="item.id" class="nav-item" :aria-label="'常用：' + item.label" :class="{ active: tab === item.id }" @click="tab = item.id"><UIcon :name="item.icon" class="size-4" /><span>{{ item.label }}</span></button></div>
          <p v-if="!visibleGroups.length" class="text-xs text-muted p-3">没有匹配菜单</p>
          <div v-for="group in visibleGroups" :key="group.id" class="nav-group">
            <button type="button" class="nav-group-caption" :aria-expanded="!!navSearch || !isCollapsed(group.id)" :aria-controls="'nav-panel-' + group.id" :title="(isCollapsed(group.id) ? '展开' : '折叠') + '「' + group.label + '」'" @click="toggleGroup(group.id)">
              <span>{{ group.label }}</span>
              <UIcon name="i-lucide-chevron-down" class="size-3 nav-group-chevron" :class="{ collapsed: !navSearch && isCollapsed(group.id) }" />
            </button>
            <div :id="'nav-panel-' + group.id" class="nav-group-items" :class="{ collapsed: !navSearch && isCollapsed(group.id) }">
              <div v-for="item in group.items" :key="item.id" class="nav-row"><button class="nav-item" :class="{ active: tab === item.id }" :aria-current="tab === item.id ? 'page' : undefined" @click="tab = item.id">
                <UIcon :name="item.icon" class="size-4" /><span>{{ item.label }}</span>
              </button><button class="nav-pin" :class="{ pinned: favorites.includes(item.id) }" :aria-label="(favorites.includes(item.id) ? '移出常用：' : '加入常用：') + item.label" :aria-pressed="favorites.includes(item.id)" :disabled="!favorites.includes(item.id) && favorites.length >= 6" @click="toggleFavorite(item.id)"><UIcon name="i-lucide-star" class="size-3.5" /></button></div>
            </div>
          </div>
        </nav>
        <div class="sidebar-footer"><UIcon name="i-lucide-shield-check" class="size-4" /><span>管理员</span></div>
      </aside>
      <main class="admin-main">
        <UAlert v-if="logoutError" :title="logoutError" color="error" role="alert" />
        <div class="admin-page-heading"><div class="breadcrumb">{{ activeGroup.label }} <UIcon name="i-lucide-chevron-right" class="size-3" /> {{ activeTab.label }}</div><h1>{{ activeTab.label }}</h1></div>
        <KeepAlive :max="25"><component :is="views[tab]" :user="props.user" @configure="tab = 'llm'" /></KeepAlive>
      </main>
    </div>
  </div>
</template>

<style scoped>
.nav-search { padding:8px 12px 12px; }
.nav-row { display:flex;align-items:center;min-width:0; }
.nav-row .nav-item { flex:1;min-width:0; }
.nav-row .nav-item span { overflow:hidden;text-overflow:ellipsis; }
.nav-pin { flex:none;width:30px;height:34px;display:grid;place-items:center;border-radius:5px;color:var(--ui-text-muted);cursor:pointer; }
.nav-pin:hover, .nav-pin:focus-visible, .nav-pin.pinned { color:var(--ui-primary);background:var(--ui-bg-accented); }
.nav-pin:disabled { opacity:0.3;cursor:default; }
.favorite-nav { padding-bottom:10px;margin-bottom:8px;border-bottom:1px solid var(--ui-border); }
@media(max-width:800px) { .nav-search { display:none; } }

.mobile-nav { display:none }
@media (max-width: 800px) { .mobile-nav { display:flex; align-items:center; gap:12px; padding:10px 16px; width:100% } .mobile-nav select { flex:1; min-width:0; padding:8px; border:1px solid var(--ui-border); border-radius:6px; background:var(--ui-bg) } .admin-sidebar nav, .sidebar-footer { display:none !important } }
</style>
