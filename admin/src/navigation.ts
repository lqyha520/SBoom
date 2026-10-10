import { onBeforeUnmount, reactive, watch, type Ref } from 'vue'

export const adminTabs = ['overview', 'llm', 'users', 'papers', 'miniUsers', 'adminAccounts', 'supportCenter',
  'topics', 'catalogTags', 'resourceRequests', 'accountClosures', 'membershipPlans', 'membershipCards',
  'orders', 'reconciliations', 'delivery', 'miniAnalytics', 'categories', 'banners', 'notices', 'documents',
  'dictionary', 'typeAccess', 'feedback', 'logs'] as const
export type AdminTab = typeof adminTabs[number]
const remembered = new Map<string, string>()
const leaveGuards = new Set<() => boolean>()
export function useAdminLeaveGuard(guard: () => boolean) { leaveGuards.add(guard); onBeforeUnmount(() => leaveGuards.delete(guard)) }
export function canLeaveAdmin() { return [...leaveGuards].every(guard => guard()) }
function canLeave(tab: AdminTab) { return tab === adminRoute.tab || canLeaveAdmin() }
export function parseAdminRoute(hash: string) {
  const [name, query = ''] = hash.replace(/^#/, '').split('?')
  const tab: AdminTab = adminTabs.includes(name as AdminTab) ? name as AdminTab : 'overview'
  return { tab, query }
}
export const adminRoute = reactive(parseAdminRoute(window.location.hash))
export function readAdminRoute() {
  const next = parseAdminRoute(window.location.hash)
  if (!canLeave(next.tab)) { window.history.replaceState(null, '', '#' + adminRoute.tab + (adminRoute.query ? '?' + adminRoute.query : '')); return }
  Object.assign(adminRoute, next)
  remembered.set(adminRoute.tab, adminRoute.query)
}
export function navigateAdmin(tab: AdminTab, values?: Record<string, string>, replace = false) {
  if (!canLeave(tab)) return
  const query = values ? new URLSearchParams(values).toString() : remembered.get(tab) || ''
  const hash = '#' + tab + (query ? '?' + query : '')
  if (window.location.hash !== hash) window.history[replace ? 'replaceState' : 'pushState'](null, '', hash)
  Object.assign(adminRoute, parseAdminRoute(hash)); remembered.set(adminRoute.tab, adminRoute.query)
}
export function listenAdminRoute() {
  readAdminRoute()
  window.addEventListener('popstate', readAdminRoute)
  window.addEventListener('hashchange', readAdminRoute)
  return () => {
    window.removeEventListener('popstate', readAdminRoute)
    window.removeEventListener('hashchange', readAdminRoute)
    remembered.clear()
  }
}

/** Keep list state in the URL; restoring history must not trigger filter-reset watchers. */
export function useAdminListRoute(tab: AdminTab, fields: Record<string, Ref<string> | Ref<number>>, reload?: () => void) {
  const defaults = Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, field.value]))
  const state = reactive({ restoring: false })
  function restore() {
    if (adminRoute.tab !== tab) return
    const params = new URLSearchParams(adminRoute.query)
    const values: Record<string, string | number> = {}
    for (const [key, field] of Object.entries(fields)) {
      const raw = params.get(key)
      values[key] = typeof defaults[key] === 'number'
        ? Math.max(1, Math.min(100000, Number.isInteger(Number(raw)) && Number(raw) > 0 ? Number(raw) : Number(defaults[key])))
        : (raw ?? String(defaults[key])).slice(0, 240)
    }
    if (Object.entries(fields).every(([key, field]) => field.value === values[key])) return
    state.restoring = true
    Object.entries(fields).forEach(([key, field]) => { field.value = values[key] })
    // Existing Vue watchers use the same queue, so clear the guard afterwards.
    queueMicrotask(() => { state.restoring = false; reload?.() })
  }
  restore()
  watch(() => [adminRoute.tab, adminRoute.query], restore, { flush: 'sync' })
  watch(Object.values(fields), () => {
    if (state.restoring || adminRoute.tab !== tab) return
    const params = new URLSearchParams(adminRoute.query)
    const searchOnly = Object.entries(fields).every(([key, field]) => key === 'q' || String(field.value) === (params.get(key) ?? String(defaults[key])))
    for (const [key, field] of Object.entries(fields)) {
      if (field.value === defaults[key]) params.delete(key)
      else params.set(key, String(field.value))
    }
    navigateAdmin(tab, Object.fromEntries(params), searchOnly)
  }, { flush: 'post' })
  return state
}
