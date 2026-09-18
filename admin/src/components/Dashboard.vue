<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as api from '../api'
import { adminRoute, navigateAdmin, listenAdminRoute } from '../navigation'

const props = defineProps<{ user: api.UserInfo }>()
const emit = defineEmits<{ logout: [] }>()
const views = {
  overview: defineAsyncComponent(() => import('./OverviewPage.vue')),
  llm: defineAsyncComponent(() => import('./ModelSettings.vue')),
  users: defineAsyncComponent(() => import('./UsersPage.vue')),
  papers: defineAsyncComponent(() => import('./PublicPapers.vue')),
  miniUsers: defineAsyncComponent(() => import('./MiniUsers.vue')),
  adminAccounts: defineAsyncComponent(() => import('./AdminAccounts.vue')),
  supportCenter: defineAsyncComponent(() => import('./SupportCenter.vue')),
  topics: defineAsyncComponent(() => import('./TopicManager.vue')),
  catalogTags: defineAsyncComponent(() => import('./CatalogTags.vue')),
  resourceRequests: defineAsyncComponent(() => import('./ResourceRequests.vue')),
  accountClosures: defineAsyncComponent(() => import('./AccountClosures.vue')),
  membershipPlans: defineAsyncComponent(() => import('./MembershipPlans.vue')),
  membershipCards: defineAsyncComponent(() => import('./MembershipCards.vue')),
  orders: defineAsyncComponent(() => import('./OrderManager.vue')),
  reconciliations: defineAsyncComponent(() => import('./Reconciliations.vue')),
  delivery: defineAsyncComponent(() => import('./DeliveryStatus.vue')),
  miniAnalytics: defineAsyncComponent(() => import('./MiniAnalytics.vue')),
  categories: defineAsyncComponent(() => import('./CategoryManager.vue')),
  banners: defineAsyncComponent(() => import('./BannerManager.vue')),
  notices: defineAsyncComponent(() => import('./NoticeManager.vue')),
  documents: defineAsyncComponent(() => import('./DocumentManager.vue')),
  dictionary: defineAsyncComponent(() => import('./DictionaryManager.vue')),
  typeAccess: defineAsyncComponent(() => import('./TypeAccessRules.vue')),
  feedback: defineAsyncComponent(() => import('./FeedbackPage.vue')),
  logs: defineAsyncComponent(() => import('./LogsPage.vue')),
}
type Tab = keyof typeof views
interface NavItem { id: Tab; label: string; icon: string }
interface NavGroup { id: string; label: string; items: NavItem[] }
const groups: NavGroup[] = [
  {
    id: 'authoring',
    label: '出题管理',
    items: [
      { id: 'overview', label: '运行概览', icon: 'i-lucide-layout-dashboard' },
      { id: 'papers', label: '公共习题', icon: 'i-lucide-library' },
      { id: 'typeAccess', label: '题型权限', icon: 'i-lucide-shield-check' },
      { id: 'users', label: '出题用户', icon: 'i-lucide-users-round' },
      { id: 'feedback', label: '用户反馈', icon: 'i-lucide-message-square-text' },
    ],
  },
  {
    id: 'mini',
    label: '小程序管理',
    items: [
      { id: 'miniUsers', label: '小程序用户', icon: 'i-lucide-contact-round' },
      { id: 'supportCenter', label: '服务与反馈', icon: 'i-lucide-messages-square' },
      { id: 'topics', label: '专题合集', icon: 'i-lucide-folders' },
      { id: 'catalogTags', label: '教材与知识点', icon: 'i-lucide-tags' },
      { id: 'resourceRequests', label: '资料需求', icon: 'i-lucide-list-plus' },
      { id: 'accountClosures', label: '注销申请', icon: 'i-lucide-user-round-x' },
      { id: 'delivery', label: '订阅提醒', icon: 'i-lucide-bell-ring' },
      { id: 'categories', label: '分类管理', icon: 'i-lucide-folder-tree' },
      { id: 'banners', label: '首页 Banner', icon: 'i-lucide-gallery-horizontal-end' },
      { id: 'notices', label: '公告与弹窗', icon: 'i-lucide-megaphone' },
      { id: 'documents', label: '协议与隐私页', icon: 'i-lucide-scroll-text' },
      { id: 'dictionary', label: '年级科目字典', icon: 'i-lucide-list-tree' },
      { id: 'miniAnalytics', label: '内容数据看板', icon: 'i-lucide-chart-column' },
    ],
  },
  {
    id: 'commerce',
    label: '会员与支付',
    items: [
      { id: 'membershipPlans', label: '会员套餐', icon: 'i-lucide-badge-check' },
      { id: 'membershipCards', label: '会员卡密', icon: 'i-lucide-key-round' },
      { id: 'orders', label: '会员订单', icon: 'i-lucide-receipt-text' },
      { id: 'reconciliations', label: '账单核对', icon: 'i-lucide-file-check-2' },
    ],
  },
  {
    id: 'system',
    label: '系统设置',
    items: [
      { id: 'adminAccounts', label: '管理员账号', icon: 'i-lucide-shield-check' },
      { id: 'llm', label: '模型配置', icon: 'i-lucide-cpu' },
      { id: 'logs', label: '系统日志', icon: 'i-lucide-terminal' },
    ],
  },
]
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
watch(tab, value => {
  const group = groups.find(item => item.items.some(entry => entry.id === value))
  if (group && isCollapsed(group.id)) { collapsed.value = collapsed.value.filter(id => id !== group.id); persistCollapsed() }
})
const activeTab = computed(() => flat.value.find(item => item.id === tab.value)!)
const activeGroup = computed(() => groups.find(group => group.items.some(item => item.id === tab.value))!)
const loggingOut = ref(false)
async function logout() {
  if (loggingOut.value) return
  loggingOut.value = true
  await api.logout()
  emit('logout')
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-header">
      <a class="brand" href="/"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div><div class="brand-name">Learning Coach</div><div class="brand-caption">管理控制台</div></div></a>
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
        <nav aria-label="管理后台导航">
          <div v-for="group in groups" :key="group.id" class="nav-group">
            <button type="button" class="nav-group-caption" :aria-expanded="!isCollapsed(group.id)" :aria-controls="'nav-panel-' + group.id" :title="(isCollapsed(group.id) ? '展开' : '折叠') + '「' + group.label + '」'" @click="toggleGroup(group.id)">
              <span>{{ group.label }}</span>
              <UIcon name="i-lucide-chevron-down" class="size-3 nav-group-chevron" :class="{ collapsed: isCollapsed(group.id) }" />
            </button>
            <div :id="'nav-panel-' + group.id" class="nav-group-items" :class="{ collapsed: isCollapsed(group.id) }">
              <button v-for="item in group.items" :key="item.id" class="nav-item" :class="{ active: tab === item.id }" :aria-current="tab === item.id ? 'page' : undefined" @click="tab = item.id">
                <UIcon :name="item.icon" class="size-4" /><span>{{ item.label }}</span>
              </button>
            </div>
          </div>
        </nav>
        <div class="sidebar-footer"><UIcon name="i-lucide-shield-check" class="size-4" /><span>管理员</span></div>
      </aside>
      <main class="admin-main">
        <div class="admin-page-heading"><div class="breadcrumb">{{ activeGroup.label }} <UIcon name="i-lucide-chevron-right" class="size-3" /> {{ activeTab.label }}</div><h1>{{ activeTab.label }}</h1></div>
        <KeepAlive><component :is="views[tab]" :user="props.user" @configure="tab = 'llm'" /></KeepAlive>
      </main>
    </div>
  </div>
</template>
