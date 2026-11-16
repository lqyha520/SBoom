import { afterEach, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, withDirectives } from 'vue'
import { allowedAdminGroups, searchAdminNavigation } from '../admin-navigation'
import { adminRoute, ensureAdminRoute, navigateAdmin, readAdminRoute } from '../navigation'
import { canAdmin, permissionDirective, setAdminIdentity } from '../permissions'

const identity = (grants: Record<string, string[]>) => setAdminIdentity({ id: 4, username: 'limited', role: 'admin', admin_permissions: grants })
afterEach(() => { history.replaceState(null, '', '/admin/'); Object.assign(adminRoute, { tab: 'overview', query: '' }) })

it('缺失授权默认拒绝，普通管理员无法取得授权管理菜单', () => {
  setAdminIdentity({ id: 4, username: 'limited', role: 'admin' })
  expect(canAdmin('papers')).toBe(false)
  identity({ adminAccounts: ['view', 'update'], papers: ['view', 'create'] })
  expect(canAdmin('adminAccounts')).toBe(false)
  expect(canAdmin('papers', 'create')).toBe(true)
  expect(canAdmin('papers', 'update')).toBe(false)
  expect(canAdmin('papers', 'delete')).toBe(false)
})

it('侧栏合并入口与快速导航只展示获授权的具体页面', () => {
  identity({ xhsDrafts: ['view'], supportCenter: ['view'] })
  const visible = allowedAdminGroups().flatMap(group => group.items.map(item => item.id))
  expect(visible).toEqual(['xhsDrafts', 'supportCenter', 'accountSecurity'])
  expect(searchAdminNavigation('', true).flatMap(group => group.items.map(item => item.id))).toEqual(['xhsDrafts', 'supportCenter', 'accountSecurity'])
  expect(canAdmin('accountSecurity')).toBe(true)
  expect(canAdmin('accountSecurity', 'delete')).toBe(true)
  expect(searchAdminNavigation('管理员', true)).toEqual([])
})

it('直接地址及历史跳转不能打开未授权页面，新增地址也检查新增权限', () => {
  identity({ categories: ['view'] })
  Object.assign(adminRoute, { tab: 'adminAccounts', query: '' })
  history.replaceState(null, '', '/admin/#adminAccounts')
  readAdminRoute()
  expect(adminRoute.tab).toBe('categories')
  navigateAdmin('papers')
  expect(adminRoute.tab).toBe('categories')
  navigateAdmin('categories', { new: '1' })
  expect(adminRoute.query).toBe('')
  identity({ notices: ['view'] })
  ensureAdminRoute()
  expect(adminRoute.tab).toBe('notices')
})

it('操作按钮随授权撤销变为隐藏且不可交互，再授权可恢复', async () => {
  identity({ papers: ['view', 'create'] })
  const wrapper = mount(defineComponent({ setup: () => () => withDirectives(h('button', '新增'), [[permissionDirective, 'papers:create']]) }))
  expect(wrapper.attributes('data-permission-denied')).toBeUndefined()
  identity({ papers: ['view'] }); await nextTick()
  expect(wrapper.attributes('data-permission-denied')).toBe('')
  expect((wrapper.element as HTMLElement).inert).toBe(true)
  identity({ papers: ['view', 'create'] }); await nextTick()
  expect(wrapper.attributes('data-permission-denied')).toBeUndefined()
  wrapper.unmount()
})
