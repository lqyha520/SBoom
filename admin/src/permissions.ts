import { shallowRef, watchEffect, type ObjectDirective } from 'vue'
import type { UserInfo } from '../../shared/user'

export type AdminAction = 'view' | 'create' | 'update' | 'delete' | 'export' | 'publish' | 'run'
export const adminIdentity = shallowRef<UserInfo | null>(null)
export function setAdminIdentity(user: UserInfo | null) { adminIdentity.value = user }
export function canAdmin(menu: string, action: AdminAction = 'view') {
  const user = adminIdentity.value
  if (user?.role !== 'admin') return false
  if (menu === 'accountSecurity') return ['view', 'delete'].includes(action)
  if (user.is_super_admin) return true
  const aliases: Record<string, string[]> = {
    referralEarnings: ['settlements'], referralRules: ['referrals'],
    financeOverview: ['settlementCosts', 'settlementReview', 'settlementPayout', 'reconciliations'],
    financeSettlements: ['settlementCosts', 'settlementReview', 'settlementPayout'],
    financePayments: ['settlementPayout'], financeBills: ['settlementCosts', 'reconciliations'],
    financeExpenses: ['settlementCosts'], financeMonthly: ['settlementCosts', 'settlementReview', 'settlementPayout'],
    financeSettings: [],
  }
  if (menu in aliases) return aliases[menu]!.some(key => {
    const grants = user.admin_permissions?.[key] || []
    return grants.includes('view') && grants.includes(action)
  })
  const grants = user.admin_permissions?.[menu] || []
  return menu !== 'adminAccounts' && grants.includes('view') && grants.includes(action)
}
export function canPermission(permission: string) {
  const [menu = '', action = 'view'] = permission.split(':')
  return canAdmin(menu, action as AdminAction)
}
const disposers = new WeakMap<HTMLElement, () => void>()
function apply(el: HTMLElement, permission: string) {
  disposers.get(el)?.()
  disposers.set(el, watchEffect(() => {
    const denied = !canPermission(permission)
    el.toggleAttribute('data-permission-denied', denied)
    el.inert = denied
  }))
}
/** 界面随权限刷新隐藏操作；服务端独立检查每次请求。 */
export const permissionDirective: ObjectDirective<HTMLElement, string> = {
  mounted: (el, binding) => apply(el, binding.value),
  updated: (el, binding) => { if (binding.value !== binding.oldValue) apply(el, binding.value) },
  unmounted: el => { disposers.get(el)?.(); disposers.delete(el) },
}
