<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { zh_cn } from '@nuxt/ui/locale'
import { useExamStore } from './stores/exam'
import { UID_KEY, useAuthStore } from './stores/auth'
import { AUTH_CHANGED_EVENT } from './api'
const LeftPanel = defineAsyncComponent(() => import('./components/LeftPanel.vue'))
const MiddleColumn = defineAsyncComponent(() => import('./components/MiddleColumn.vue'))
const PreviewPane = defineAsyncComponent(() => import('./components/PreviewPane.vue'))
const StepResult = defineAsyncComponent(() => import('./components/StepResult.vue'))
const AdvancedDrawer = defineAsyncComponent(() => import('./components/AdvancedDrawer.vue'))
const MyTemplatesDialog = defineAsyncComponent(() => import('./components/MyTemplatesDialog.vue'))
const HistoryDialog = defineAsyncComponent(() => import('./components/HistoryDialog.vue'))
const CloudLibraryDialog = defineAsyncComponent(() => import('./components/CloudLibraryDialog.vue'))

const LoginView = defineAsyncComponent(() => import('./components/LoginView.vue'))
const store = useExamStore()
const auth = useAuthStore()
const showAdv = ref(false)
const showTpl = ref(false)
const showHistory = ref(false)
const showCloud = ref(false)
const accountError = ref('')
const accountReloading = ref(false)
const draftLabel = computed(() => ({ loading: '读取草稿', saving: '正在保存', saved: store.draftSavedAt ? '草稿已保存' : '本机草稿', error: '保存失败' })[store.draftState])
const mobilePanel = ref('conditions')
const workspaceTabs = [
  { label: '出题条件', value: 'conditions', icon: 'i-lucide-sliders-horizontal' },
  { label: '试卷结构', value: 'structure', icon: 'i-lucide-list-tree' },
  { label: '卷面预览', value: 'preview', icon: 'i-lucide-file-text' },
]
const userMenu = computed(() => [
  [{ label: '云端试卷', icon: 'i-lucide-cloud', onSelect: () => { showCloud.value = true } }],
  ...(auth.user?.role === 'admin' ? [[{ label: '后台管理', icon: 'i-lucide-shield-check', href: '/admin/' }]] : []),
  [{ label: '退出登录', icon: 'i-lucide-log-out', onSelect: async () => {
    if (!await store.flushDraft()) {
      accountError.value = '草稿未保存，暂未退出登录；请稍后重试'
      return
    }
    try { await auth.logout() }
    catch { accountError.value = '退出登录失败，请检查网络后重试' }
  } }],
])
async function accountChanged() {
  if (accountReloading.value) return
  accountReloading.value = true
  try {
    if (await store.suspendForAccountChange()) location.reload()
    else accountError.value = '账号已变化，草稿尚未保存；当前页面已保留，暂未刷新'
  } finally {
    accountReloading.value = false
  }
}
function storageChanged(event: StorageEvent) {
  if (event.key === UID_KEY && event.newValue !== store.ownerId) void accountChanged()
}
function saveOnHide() { if (document.visibilityState === 'hidden') void store.flushDraft() }
function saveOnExit() { void store.flushDraft() }
function warnUnsaved(event: BeforeUnloadEvent) {
  if (store.draftState === 'saving' || store.draftState === 'error') {
    event.preventDefault()
    event.returnValue = ''
  }
}
function syncOnReconnect() { void store.syncTemplatesFromServer() }
onMounted(() => {
  if (auth.user) void store.init()
  window.addEventListener(AUTH_CHANGED_EVENT, accountChanged)
  window.addEventListener('storage', storageChanged)
  window.addEventListener('online', syncOnReconnect)
  window.addEventListener('pagehide', saveOnExit)
  window.addEventListener('beforeunload', warnUnsaved)
  document.addEventListener('visibilitychange', saveOnHide)
})
onBeforeUnmount(() => {
  store.disposePersistence()
  window.removeEventListener(AUTH_CHANGED_EVENT, accountChanged)
  window.removeEventListener('storage', storageChanged)
  window.removeEventListener('online', syncOnReconnect)
  window.removeEventListener('pagehide', saveOnExit)
  window.removeEventListener('beforeunload', warnUnsaved)
  document.removeEventListener('visibilitychange', saveOnHide)
})
</script>

<template>
  <UApp :locale="zh_cn" :toaster="{ position: 'top-right' }">
    <div v-if="!auth.ready" class="loading-screen" role="status">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
      <p>正在加载工作台</p>
    </div>
    <LoginView v-else-if="!auth.user" />
    <div v-else class="app-shell">
      <header class="topbar no-print">
        <div class="brand">
          <span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span>
          <div><div class="brand-name">出题工作台</div><div class="brand-caption">Learning Coach</div></div>
        </div>
        <nav class="top-nav" aria-label="工作台导航">
          <button :class="{ active: store.view === 'build' }" :aria-current="store.view === 'build' ? 'page' : undefined" @click="store.backToBuild()">
            <UIcon name="i-lucide-panels-top-left" class="size-4" /><span>试卷搭建</span>
          </button>
          <button :class="{ active: store.view === 'result' }" :disabled="!store.papers.length" :aria-current="store.view === 'result' ? 'page' : undefined" @click="store.view = 'result'">
            <UIcon name="i-lucide-files" class="size-4" /><span>生成结果</span><span v-if="store.papers.length" class="nav-count">{{ store.papers.length }}</span>
          </button>
        </nav>
        <div class="topbar-actions">
          <UTooltip text="云端试卷"><UButton icon="i-lucide-cloud" color="neutral" variant="ghost" aria-label="云端试卷" class="icon-tool" @click="showCloud = true" /></UTooltip>
          <UTooltip text="本机历史"><UButton icon="i-lucide-history" color="neutral" variant="ghost" aria-label="本机历史" class="icon-tool" @click="showHistory = true" /></UTooltip>
          <UButton icon="i-lucide-folder-open" label="我的模板" aria-label="我的模板" color="neutral" variant="ghost" class="templates-button" @click="showTpl = true" />
          <UTooltip text="卷面设置">
            <UButton icon="i-lucide-settings-2" color="neutral" variant="ghost" aria-label="卷面设置" class="icon-tool" @click="showAdv = true" />
          </UTooltip>
          <div class="header-divider"></div>
          <UDropdownMenu :items="userMenu">
            <UButton color="neutral" variant="ghost" :aria-label="'账号菜单：' + auth.user.username" class="account-button">
              <span class="user-avatar">{{ auth.user.username.slice(0, 1).toUpperCase() }}</span>
              <span class="account-name">{{ auth.user.username }}</span>
              <UIcon name="i-lucide-chevron-down" class="size-3 text-muted" />
            </UButton>
          </UDropdownMenu>
        </div>
      </header>
      <div class="workspace-heading no-print">
        <div class="workspace-title">
          <h1>{{ store.view === 'build' ? '试卷搭建' : '生成结果' }}</h1>
          <UBadge v-if="store.grade" color="neutral" variant="subtle" size="sm">{{ store.grade }}{{ store.subject ? ' / ' + store.subject : '' }}</UBadge>
        </div>
        <div class="workspace-meta">
          <span class="draft-state" :class="{ 'text-error': store.draftState === 'error' }" role="status" :title="store.draftSavedAt ? '本机保存于 ' + new Date(store.draftSavedAt).toLocaleString() : ''"><UIcon :name="store.draftState === 'saving' ? 'i-lucide-loader-circle' : store.draftState === 'error' ? 'i-lucide-cloud-off' : 'i-lucide-hard-drive'" class="size-3.5" :class="{ 'animate-spin': store.draftState === 'saving' }" />{{ draftLabel }}</span>
          <span v-if="store.generating" role="status" class="generation-state"><UIcon name="i-lucide-loader-circle" class="size-3.5 animate-spin" />{{ store.generateProgress || '正在生成' }}</span>
          <template v-else><span class="status-dot"></span><span>{{ store.sections.length }} 个大题</span><span class="meta-divider">/</span><span>{{ store.totalQuestions }} 道题目</span></template>
        </div>
      </div>
      <UAlert v-if="store.storageError || accountError" :title="accountError || store.storageError" color="warning" variant="soft" class="workspace-alert no-print" role="alert">
        <template v-if="store.accountChanged" #actions>
          <UButton icon="i-lucide-refresh-cw" label="保存并刷新" color="warning" variant="soft" :loading="accountReloading" @click="accountChanged" />
        </template>
      </UAlert>
      <UTabs v-if="store.view === 'build'" v-model="mobilePanel" :items="workspaceTabs" :content="false" class="workspace-tabs no-print" :ui="{ list: 'w-full', trigger: 'flex-1' }" />
      <div v-if="!store.persistenceReady" class="loading-screen" role="status">正在恢复草稿</div>
      <main v-else class="workbench" :class="{ 'result-only': store.view === 'result' }" :data-panel="mobilePanel">
        <template v-if="store.view === 'build'">
          <LeftPanel />
          <MiddleColumn @open-templates="showTpl = true" @preview="mobilePanel = 'preview'" />
          <PreviewPane @open-settings="showAdv = true" />
        </template>
        <StepResult v-else @library="showCloud = true" />
      </main>
      <AdvancedDrawer v-if="showAdv" :open="showAdv" @close="showAdv = false" />
      <MyTemplatesDialog v-if="showTpl" :open="showTpl" @close="showTpl = false" />
      <HistoryDialog v-if="showHistory" :open="showHistory" @close="showHistory = false" />
      <CloudLibraryDialog v-if="showCloud" :open="showCloud" @close="showCloud = false" />
    </div>
  </UApp>
</template>
