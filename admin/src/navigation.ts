import { onBeforeUnmount, reactive, watch, type Ref } from 'vue'
import { canAdmin } from './permissions'

export const adminTabs = ['overview', 'llm', 'users', 'papers', 'miniUsers', 'adminAccounts', 'supportCenter',
  'topics', 'catalogTags', 'xhsResearch', 'xhsIdeas', 'xhsMaterials', 'xhsDrafts', 'xhsPublishing', 'xhsAnalytics', 'xhsAccounts', 'xhsAssets', 'resourceRequests', 'accountClosures', 'membershipPlans', 'membershipCards', 'membershipContact',
  'orders', 'referrals', 'referralEarnings', 'referralRules', 'financeOverview', 'financeSettlements', 'financePayments', 'financeBills', 'financeExpenses', 'financeMonthly', 'financeSettings', 'settlements', 'reconciliations', 'delivery', 'miniAnalytics', 'categories', 'banners', 'notices', 'documents',
  'dictionary', 'typeAccess', 'feedback', 'logs', 'financeLedger', 'accountSecurity'] as const
export type AdminTab = typeof adminTabs[number]
const remembered = new Map<string, string>()
const leaveGuards = new Set<() => boolean>()
export function useAdminLeaveGuard(guard: () => boolean) { leaveGuards.add(guard); onBeforeUnmount(() => leaveGuards.delete(guard)) }
export function canLeaveAdmin() { return [...leaveGuards].every(guard => guard()) }
function canLeave(tab: AdminTab, query: string) {
  const same = tab === adminRoute.tab
  return (same && (!tab.startsWith('xhs') || query === adminRoute.query)) || canLeaveAdmin()
}
export function parseAdminRoute(hash: string) {
  const [name, query = ''] = hash.replace(/^#/, '').split('?')
  const tab: AdminTab = adminTabs.includes(name as AdminTab) ? name as AdminTab : 'overview'
  if (tab === 'settlements' || tab === 'reconciliations') {
    const params = new URLSearchParams(query)
    const section = params.get('section') || 'workspace'
    const financial = canAdmin('financeSettlements')
    let target: AdminTab = tab === 'reconciliations' ? 'financeBills' : financial ? 'financeSettlements' : 'referralEarnings'
    if (tab === 'reconciliations') params.set('section', 'wechat')
    else if (section === 'rules') {
      target = canAdmin('referralRules') ? 'referralRules' : 'referralEarnings'
      if (target === 'referralRules') params.delete('section')
    }
    else if (section === 'payee') target = 'referralEarnings'
    else if (financial && ['monthly', 'batches', 'bills', 'finance'].includes(section)) {
      target = ({ monthly: 'financeMonthly', batches: 'financePayments', bills: 'financeBills', finance: 'financeSettings' } as Record<string, AdminTab>)[section]!
      params.delete('section')
    }
    return { tab: target, query: params.toString() }
  }
  return { tab, query }
}
export const adminRoute = reactive(parseAdminRoute(window.location.hash))
export function readAdminRoute() {
  const next = parseAdminRoute(window.location.hash)
  if (!canAdmin(next.tab)) { ensureAdminRoute(); return }
  if (!canLeave(next.tab, next.query)) { window.history.replaceState(null, '', '#' + adminRoute.tab + (adminRoute.query ? '?' + adminRoute.query : '')); return }
  Object.assign(adminRoute, next)
  const canonical = '#' + next.tab + (next.query ? '?' + next.query : '')
  if (window.location.hash !== canonical) window.history.replaceState(null, '', canonical)
  remembered.set(adminRoute.tab, adminRoute.query)
}
export function navigateAdmin(tab: AdminTab, values?: Record<string, string>, replace = false) {
  const resolved = parseAdminRoute('#' + tab + (values ? '?' + new URLSearchParams(values) : ''))
  if (resolved.tab !== tab) { navigateAdmin(resolved.tab, Object.fromEntries(new URLSearchParams(resolved.query)), replace); return }
  if (!canAdmin(tab) || values?.new === '1' && !canAdmin(tab, 'create')) return
  const query = values ? new URLSearchParams(values).toString() : remembered.get(tab) || ''
  if (!canLeave(tab, query)) return
  const hash = '#' + tab + (query ? '?' + query : '')
  if (window.location.hash !== hash) window.history[replace ? 'replaceState' : 'pushState'](null, '', hash)
  Object.assign(adminRoute, parseAdminRoute(hash)); remembered.set(adminRoute.tab, adminRoute.query)
}
export function ensureAdminRoute() {
  const next = parseAdminRoute(window.location.hash)
  if (canAdmin(next.tab)) {
    Object.assign(adminRoute, next)
    window.history.replaceState(null, '', '#' + next.tab + (next.query ? '?' + next.query : ''))
    return
  }
  const tab = adminTabs.find(id => canAdmin(id))
  if (!tab) return
  Object.assign(adminRoute, { tab, query: '' })
  window.history.replaceState(null, '', '#' + tab)
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
