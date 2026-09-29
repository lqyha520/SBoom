<script setup lang="ts">
import { lazyComponent } from '../../shared/async-component'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useExamStore } from './stores/exam'
import { UID_KEY, useAuthStore } from './stores/auth'
import { AUTH_CHANGED_EVENT } from './api'
import { loadLeftPanel, loadMiddleColumn, loadPreviewPane } from './workspace-loaders'
import { storageUsage, type StorageUsage } from './local-storage'
const LeftPanel = lazyComponent(loadLeftPanel)
const MiddleColumn = lazyComponent(loadMiddleColumn)
const PreviewPane = lazyComponent(loadPreviewPane)
const ImageWorkbench = lazyComponent(() => import('./components/ImageWorkbench.vue'))
const StepResult = lazyComponent(() => import('./components/StepResult.vue'))
const AdvancedDrawer = lazyComponent(() => import('./components/AdvancedDrawer.vue'))
const MyTemplatesDialog = lazyComponent(() => import('./components/MyTemplatesDialog.vue'))
const HistoryDialog = lazyComponent(() => import('./components/HistoryDialog.vue'))
const CloudLibraryDialog = lazyComponent(() => import('./components/CloudLibraryDialog.vue'))

const store = useExamStore()
const auth = useAuthStore()
const showAdv = ref(false)
const showTpl = ref(false)
const showHistory = ref(false)
const showCloud = ref(false)
const imageMode = ref(false)
const imageOpened = ref(false)
const localUsage = ref<StorageUsage | null>(null)
const storageLabel = computed(() => localUsage.value ? `本机已用 ${(localUsage.value.usage / 1048576).toFixed(1)} MB / ${(localUsage.value.quota / 1048576).toFixed(0)} MB${localUsage.value.persisted ? ' · 持久保存' : ' · 请定期导出备份'}` : '本机保留最近 10 份闲置草稿、100 份历史（30 天）')
function openImages() { imageOpened.value = true; imageMode.value = true }
const accountError = ref('')
const suggestedKeyword = ref((new URLSearchParams(location.search).get('keyword') || '').slice(0, 100))
function applySuggestedKeyword() { store.keyword = suggestedKeyword.value; store.view = 'build'; suggestedKeyword.value = ''; history.replaceState(null, '', location.pathname) }
const accountReloading = ref(false)
const draftLabel = computed(() => ({ loading: '读取草稿', saving: '正在保存', saved: store.draftSavedAt ? '草稿已保存' : '本机草稿', error: '保存失败' })[store.draftState])
const mobilePanel = ref('conditions')
const workspaceTabs = [
  { label: '出题条件', value: 'conditions', icon: 'i-lucide-sliders-horizontal' },
  { label: '试卷结构', value: 'structure', icon: 'i-lucide-list-tree' },
  { label: '卷面预览', value: 'preview', icon: 'i-lucide-file-text' },
]
const userMenu = computed(() => [
  [{ label: storageLabel.value, disabled: true }],
  [{ label: '云端试卷', icon: 'i-lucide-cloud', onSelect: () => { showCloud.value = true } }],
  ...(auth.user?.role === 'admin' ? [[{ label: '后台管理', icon: 'i-lucide-shield-check', href: '/admin/' }]] : []),
  [{ label: '退出登录', icon: 'i-lucide-log-out', onSelect: async () => {
    if (!await store.flushDraft()) {
      accountError.value = '草稿未保存，暂未退出登录；请稍后重试'
      return
    }
    try { await auth.logout() }
    catch { accountError.value = '退出登录失败，请检查网络后重试' }
  } }, { label: '退出并清除本机数据', icon: 'i-lucide-trash-2', onSelect: logoutAndClear }],
])
async function logoutAndClear() {
  if (store.generating || !window.confirm('退出并清除本账号在此浏览器的草稿、历史、模板和生图结果？云端内容会保留。')) return
  try { await store.suspendForAccountChange(); await auth.logout(true) }
  catch (error) { accountError.value = error instanceof Error ? error.message : '退出或清理失败，请重试' }
}
async function accountChanged(event?: Event) {
  if (accountReloading.value) return
  accountReloading.value = true
  try {
    if (await store.suspendForAccountChange()) {
      if ((event as CustomEvent | undefined)?.detail?.expired) sessionStorage.setItem('lc_session_notice', '登录已过期，草稿已保存。重新登录后可继续编辑。')
      location.reload()
    }
    else accountError.value = '账号已变化，草稿尚未保存；当前页面已保留，暂未刷新'
  } finally {
    accountReloading.value = false
  }
}
function storageChanged(event: StorageEvent) {
  if (event.key === 'lc_purge:' + store.ownerId && event.newValue) { store.accountChanged = true; store.disposePersistence(); location.reload(); return }
  if (event.key === UID_KEY && event.newValue !== store.ownerId) void accountChanged()
}
function saveOnHide() { if (document.visibilityState === 'hidden') void store.flushDraft() }
function saveOnExit() { void store.flushDraft() }
function captureEdit(event: Event) {
  const target = event.target as HTMLElement
  if (target.isContentEditable || target.closest('[contenteditable="true"]')) store.recordEdit('rich-text')
}
function editShortcut(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (target.closest('input, textarea, [contenteditable="true"]') || !(event.ctrlKey || event.metaKey)) return
  if (event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? store.redo() : store.undo() }
  if (event.key.toLowerCase() === 'y') { event.preventDefault(); store.redo() }
}
function warnUnsaved(event: BeforeUnloadEvent) {
  if (store.draftState === 'saving' || store.draftState === 'error') {
    event.preventDefault()
    event.returnValue = ''
  }
}
function syncOnReconnect() { void store.syncTemplatesFromServer() }
onMounted(() => {
  if (auth.user) void store.init()
  void storageUsage(true).then(value => { localUsage.value = value })
  window.addEventListener(AUTH_CHANGED_EVENT, accountChanged)
  window.addEventListener('storage', storageChanged)
  window.addEventListener('online', syncOnReconnect)
  window.addEventListener('pagehide', saveOnExit)
  window.addEventListener('beforeunload', warnUnsaved)
  window.addEventListener('keydown', editShortcut)
  document.addEventListener('visibilitychange', saveOnHide)
})
onBeforeUnmount(() => {
  store.disposePersistence()
  window.removeEventListener(AUTH_CHANGED_EVENT, accountChanged)
  window.removeEventListener('storage', storageChanged)
  window.removeEventListener('online', syncOnReconnect)
  window.removeEventListener('pagehide', saveOnExit)
  window.removeEventListener('beforeunload', warnUnsaved)
  window.removeEventListener('keydown', editShortcut)
  document.removeEventListener('visibilitychange', saveOnHide)
})
</script>

<template>
    <div v-if="auth.user" class="app-shell">
      <header class="topbar no-print">
        <div class="brand">
          <span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span>
          <div><div class="brand-name">出题工作台</div><div class="brand-caption">Learning Coach</div></div>
        </div>
        <nav class="top-nav" aria-label="工作台导航">
          <button :class="{ active: !imageMode && store.view === 'build' }" :aria-current="!imageMode && store.view === 'build' ? 'page' : undefined" @click="imageMode = false; store.backToBuild()">
            <UIcon name="i-lucide-panels-top-left" class="size-4" /><span>试卷搭建</span>
          </button>
          <button :class="{ active: !imageMode && store.view === 'result' }" :disabled="!store.papers.length" :aria-current="!imageMode && store.view === 'result' ? 'page' : undefined" @click="imageMode = false; store.view = 'result'">
            <UIcon name="i-lucide-files" class="size-4" /><span>生成结果</span><span v-if="store.papers.length" class="nav-count">{{ store.papers.length }}</span>
          </button>
          <button :class="{ active: imageMode }" :aria-current="imageMode ? 'page' : undefined" @click="openImages"><UIcon name="i-lucide-image" class="size-4" /><span>图片出题</span></button>
        </nav>
        <div class="topbar-actions">
          <template v-if="!imageMode">
          <UTooltip text="撤销（Ctrl+Z）"><UButton icon="i-lucide-undo-2" aria-label="撤销编辑" variant="ghost" :disabled="!store.canUndo" @click="store.undo()" /></UTooltip>
          <UTooltip text="重做（Ctrl+Shift+Z）"><UButton icon="i-lucide-redo-2" aria-label="重做编辑" variant="ghost" :disabled="!store.canRedo" @click="store.redo()" /></UTooltip>
          <UTooltip text="云端试卷"><UButton icon="i-lucide-cloud" color="neutral" variant="ghost" aria-label="云端试卷" class="icon-tool" @click="showCloud = true" /></UTooltip>
          <UTooltip text="本机历史"><UButton icon="i-lucide-history" color="neutral" variant="ghost" aria-label="本机历史" class="icon-tool" @click="showHistory = true" /></UTooltip>
          <UButton icon="i-lucide-folder-open" label="我的模板" aria-label="我的模板" color="neutral" variant="ghost" class="templates-button" @click="showTpl = true" />
          <UTooltip text="卷面设置">
            <UButton icon="i-lucide-settings-2" color="neutral" variant="ghost" aria-label="卷面设置" class="icon-tool" @click="showAdv = true" />
          </UTooltip>
          <div class="header-divider"></div>
          </template>
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
          <h1>{{ imageMode ? '图片出题' : store.view === 'build' ? '试卷搭建' : '生成结果' }}</h1>
          <UBadge v-if="store.grade && !imageMode" color="neutral" variant="subtle" size="sm">{{ store.grade }}{{ store.subject ? ' / ' + store.subject : '' }}</UBadge>
        </div>
        <div v-if="!imageMode" class="workspace-meta">
          <span class="draft-state" :class="{ 'text-error': store.draftState === 'error' }" :title="storageLabel"><UIcon :name="store.draftState === 'saving' ? 'i-lucide-loader-circle' : store.draftState === 'error' ? 'i-lucide-cloud-off' : 'i-lucide-hard-drive'" class="size-3.5" :class="{ 'animate-spin': store.draftState === 'saving' }" />{{ draftLabel }}</span><span class="sr-only">{{ storageLabel }}</span>
          <span v-if="store.generating" role="status" class="generation-state"><UIcon name="i-lucide-loader-circle" class="size-3.5 animate-spin" />{{ store.generateProgress || '正在生成' }}</span>
          <template v-else><span class="status-dot"></span><span>{{ store.sections.length }} 个大题</span><span class="meta-divider">/</span><span>{{ store.totalQuestions }} 道题目</span></template>
        </div>
      </div>
      <UAlert v-if="store.storageError || accountError" :title="accountError || store.storageError" color="warning" variant="soft" class="workspace-alert no-print" role="alert">
        <template v-if="store.accountChanged" #actions>
          <UButton icon="i-lucide-refresh-cw" label="保存并刷新" color="warning" variant="soft" :loading="accountReloading" @click="accountChanged" />
        </template>
      </UAlert>
      <UAlert v-if="suggestedKeyword && store.persistenceReady" title="从运营统计带入的出题需求" :description="suggestedKeyword" class="workspace-alert no-print"><template #actions><UButton label="应用知识点" :disabled="store.generating" @click="applySuggestedKeyword" /><UButton label="忽略" variant="ghost" @click="suggestedKeyword = ''" /></template></UAlert>
      <UTabs v-if="!imageMode && store.view === 'build'" v-model="mobilePanel" :items="workspaceTabs" :content="false" class="workspace-tabs no-print" :ui="{ list: 'w-full', trigger: 'flex-1' }" />
      <div v-if="!store.persistenceReady" class="loading-screen" role="status">正在恢复草稿</div>
      <main v-else class="workbench" :class="{ 'result-only': imageMode || store.view === 'result' }" :data-panel="imageMode ? 'image' : mobilePanel" @beforeinput.capture="captureEdit">
        <ImageWorkbench v-if="imageOpened" v-show="imageMode" />
          <LeftPanel v-show="!imageMode && store.view === 'build'" />
          <MiddleColumn v-show="!imageMode && store.view === 'build'" @open-templates="showTpl = true" @preview="mobilePanel = 'preview'" />
          <KeepAlive><PreviewPane v-if="!imageMode && store.view === 'build'" @open-settings="showAdv = true" /></KeepAlive>
        <KeepAlive><StepResult v-if="!imageMode && store.view === 'result'" @library="showCloud = true" /></KeepAlive>
      </main>
      <AdvancedDrawer v-if="showAdv" :open="showAdv" @close="showAdv = false" />
      <MyTemplatesDialog v-if="showTpl" :open="showTpl" @close="showTpl = false" />
      <HistoryDialog v-if="showHistory" :open="showHistory" @close="showHistory = false" />
      <CloudLibraryDialog v-if="showCloud" :open="showCloud" @close="showCloud = false" />
    </div>
</template>
