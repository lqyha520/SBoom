<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type InputHTMLAttributes } from 'vue'
import { adminGroups, searchAdminNavigation, type NavItem } from '../admin-navigation'
import { adminRoute, navigateAdmin, type AdminTab } from '../navigation'

const props = defineProps<{ userId: number; favorites: NavItem[] }>()
const open = ref(false)
const query = ref('')
const shortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘ K' : 'Ctrl K'
const searchInput = { 'aria-label': '搜索管理页面', maxlength: 80 } satisfies InputHTMLAttributes
const storageKey = `lc-admin-recent:${props.userId}`
const items = adminGroups.flatMap(group => group.items)
const recent = ref<AdminTab[]>(readRecent())

function readRecent(): AdminTab[] {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(storageKey) || '[]')
    if (Array.isArray(saved)) return [...new Set(saved.filter((id): id is AdminTab => items.some(item => item.id === id)))].slice(0, 5)
  } catch { /* 无法存储时，仍可使用本次页面中的最近访问。 */ }
  return []
}

watch(() => adminRoute.tab, id => {
  recent.value = [id, ...recent.value.filter(value => value !== id)].slice(0, 5)
  try { sessionStorage.setItem(storageKey, JSON.stringify(recent.value)) } catch { /* 隐私模式下保留内存状态。 */ }
}, { immediate: true })
watch(open, value => { if (value) query.value = '' })

function select(id: AdminTab) {
  navigateAdmin(id)
  // 离开保护被取消时保留搜索面板和输入。
  if (adminRoute.tab === id) open.value = false
}

function command(item: NavItem) {
  return {
    ...item,
    description: adminGroups.find(group => group.items.some(entry => entry.id === item.id))?.label,
    active: item.id === adminRoute.tab,
    onSelect: () => select(item.id),
  }
}

const commandGroups = computed(() => {
  if (query.value.trim()) return searchAdminNavigation(query.value).map(group => ({
    id: group.id, label: group.label, ignoreFilter: true, items: group.items.map(command),
  }))
  const recentItems = recent.value.flatMap(id => items.filter(item => item.id === id && id !== adminRoute.tab))
  const seen = new Set(recentItems.map(item => item.id))
  const favorites = props.favorites.filter(item => !seen.has(item.id) && item.id !== adminRoute.tab)
  favorites.forEach(item => seen.add(item.id))
  return [
    { id: 'recent', label: '最近访问', ignoreFilter: true, items: recentItems.map(command) },
    { id: 'favorites', label: '常用入口', ignoreFilter: true, items: favorites.map(command) },
    { id: 'all', label: '全部页面', ignoreFilter: true, items: items.filter(item => !seen.has(item.id)).map(command) },
  ].filter(group => group.items.length)
})

function onShortcut(event: KeyboardEvent) {
  if (event.defaultPrevented || event.isComposing || event.repeat || event.altKey || event.shiftKey) return
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'k') return
  // 编辑弹窗或重新验证期间，不再叠加一层导航。
  if (!open.value && document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"]')) return
  event.preventDefault()
  open.value = !open.value
}
onMounted(() => window.addEventListener('keydown', onShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', onShortcut))
</script>

<template>
  <UModal v-model:open="open" title="快速导航" description="搜索管理页面，也可以从最近访问和常用入口继续工作。" :ui="{ content: 'max-w-xl overflow-hidden rounded-2xl' }">
    <UButton color="neutral" variant="outline" class="navigation-search-trigger" aria-label="搜索页面" aria-keyshortcuts="Control+k Meta+k">
      <UIcon name="i-lucide-search" class="size-4" />
      <span class="navigation-search-label">搜索页面…</span>
      <kbd class="navigation-shortcut">{{ shortcut }}</kbd>
    </UButton>
    <template #content>
      <div class="navigation-search-heading"><span><UIcon name="i-lucide-compass" class="size-4" />快速导航</span><span>快速找到你的工作入口</span></div>
      <UCommandPalette
        v-model:search-term="query"
        :groups="commandGroups"
        :input="searchInput"
        :close="{ 'aria-label': '关闭快速导航' }"
        :ui="{ content: 'h-[min(360px,45dvh)]', item: 'py-3 rounded-lg', label: 'text-xs font-medium' }"
        placeholder="输入页面名称，例如：订单、资料、模型"
        @update:open="open = $event"
      >
        <template #item-trailing="{ item }"><span v-if="item.active" class="navigation-current">当前页面</span><UIcon v-else name="i-lucide-arrow-up-right" class="size-4 text-muted" /></template>
        <template #empty>
          <div class="navigation-search-empty"><UIcon name="i-lucide-search-x" class="size-8" /><strong>没有找到相关页面</strong><p>试试“资料”“会员”或“系统设置”。</p><UButton label="查看全部页面" color="neutral" variant="outline" size="sm" @click="query = ''" /></div>
        </template>
        <template #footer>
          <div class="navigation-search-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 选择 <kbd>Enter</kbd> 打开</span><span><kbd>Esc</kbd> 关闭</span></div>
        </template>
      </UCommandPalette>
    </template>
  </UModal>
</template>

<style scoped>
.navigation-search-trigger { gap:9px;min-height:36px;border-radius:9px;color:var(--ui-text-muted);background:#f8faf9; }
.navigation-search-label { font-size:12px; }
.navigation-shortcut { margin-left:12px;font-size:10px;font-family:inherit;padding:2px 5px;border:1px solid var(--ui-border);border-radius:4px;background:#fff; }
.navigation-search-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px 10px;font-size:11px;color:var(--ui-text-muted); }
.navigation-search-heading > :first-child { display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;color:#32745b; }
.navigation-current { font-size:10px;background:#edf7f2;color:#32745b;padding:3px 6px;border-radius:5px;white-space:nowrap; }
.navigation-search-empty { display:flex;flex-direction:column;align-items:center;gap:10px;padding:36px 16px;text-align:center; }
.navigation-search-empty strong { font-size:14px;color:var(--ui-text); }
.navigation-search-empty p { font-size:12px; }
.navigation-search-footer { display:flex;justify-content:space-between;gap:8px;width:100%;padding:10px 16px;background:#f6f9f7;border-top:1px solid var(--ui-border-muted);font-size:11px;color:var(--ui-text-muted); }
.navigation-search-footer kbd { display:inline-block;margin-right:4px;padding:1px 4px;border:1px solid var(--ui-border);border-radius:4px;background:#fff;font-family:inherit; }
@media(max-width:1280px) { .navigation-search-label, .navigation-shortcut { display:none; }.navigation-search-trigger { width:36px;justify-content:center;padding:0; } }
@media(max-width:800px) { .navigation-search-trigger { width:40px;min-height:40px; }.navigation-search-footer > :first-child { visibility:hidden; } }
@media(max-width:380px) { .navigation-search-heading > :last-child { display:none; } }
</style>
