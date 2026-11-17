import { afterEach, expect, it } from 'vitest'
import { setAdminIdentity, canAdmin } from '../permissions'
import { adminRoute, navigateAdmin, parseAdminRoute } from '../navigation'
import { allowedAdminGroups } from '../admin-navigation'

afterEach(() => { history.replaceState(null, '', '/admin/'); Object.assign(adminRoute, { tab: 'overview', query: '' }) })
it('财务菜单按原职责开放，费用核对不获得付款和推广管理权限', () => {
  setAdminIdentity({ id: 5, username: 'costs', role: 'admin', admin_permissions: { settlements: ['view'], settlementCosts: ['view', 'run'] } })
  const groups = allowedAdminGroups()
  expect(groups.find(group => group.id === 'finance')?.items.map(item => item.id)).toEqual(['financeOverview', 'financeSettlements', 'financeBills', 'financeExpenses', 'financeMonthly'])
  expect(canAdmin('financePayments')).toBe(false)
  expect(canAdmin('referrals')).toBe(false)
  expect(canAdmin('financeSettings')).toBe(false)
})
it('旧财务链接迁移到独立页面并保留筛选，个人入口始终可直接进入', () => {
  setAdminIdentity({ id: 1, username: 'root', role: 'admin', is_super_admin: true })
  expect(parseAdminRoute('#settlements?section=batches')).toEqual({ tab: 'financePayments', query: '' })
  expect(parseAdminRoute('#settlements?mode=statements&admin=5&status=approved').tab).toBe('financeSettlements')
  expect(parseAdminRoute('#reconciliations?page=3')).toEqual({ tab: 'financeBills', query: 'page=3&section=wechat' })
  navigateAdmin('referralEarnings')
  expect(adminRoute.tab).toBe('referralEarnings')
})
it('推广人旧结算地址进入个人收益，不能由地址获得财务页面', () => {
  setAdminIdentity({ id: 6, username: 'promoter', role: 'admin', admin_permissions: { settlements: ['view', 'create'], referrals: ['view'] } })
  expect(parseAdminRoute('#settlements?mode=requests').tab).toBe('referralEarnings')
  navigateAdmin('referralEarnings', { mode: 'requests' })
  navigateAdmin('financePayments')
  expect(adminRoute.tab).toBe('referralEarnings')
  expect(allowedAdminGroups().some(group => group.id === 'finance')).toBe(false)
})
it('仅有个人结算查看权限时，旧奖励规则链接保留在个人只读规则页', () => {
  setAdminIdentity({ id: 7, username: 'earnings-only', role: 'admin', admin_permissions: { settlements: ['view'] } })
  expect(parseAdminRoute('#settlements?section=rules')).toEqual({ tab: 'referralEarnings', query: 'section=rules' })
})
