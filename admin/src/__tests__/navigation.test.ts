import { afterEach, beforeEach, expect, it } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { adminRoute, listenAdminRoute, navigateAdmin, parseAdminRoute, readAdminRoute, useAdminListRoute } from '../navigation'
let stop: () => void
beforeEach(() => { history.replaceState(null, '', '/admin/'); stop = listenAdminRoute() })
afterEach(() => stop())

it('直接链接恢复页面、筛选和页码，浏览器历史恢复不重置页码', async () => {
  history.replaceState(null, '', '#papers?q=%E6%95%B0%E5%AD%A6&status=draft&page=3'); readAdminRoute()
  const scope = effectScope(), q = ref(''), status = ref('all'), page = ref(1)
  scope.run(() => useAdminListRoute('papers', { q, status, page }))
  await nextTick()
  expect([adminRoute.tab, q.value, status.value, page.value]).toEqual(['papers', '数学', 'draft', 3])
  page.value = 4; await nextTick()
  expect(location.hash).toContain('page=4')
  history.replaceState(null, '', '#papers?q=english&status=published&page=2')
  window.dispatchEvent(new PopStateEvent('popstate')); await nextTick()
  expect([q.value, status.value, page.value]).toEqual(['english', 'published', 2])
  scope.stop()
})

it('切换后台菜单后返回，保留原页面筛选；非法菜单回到概览', () => {
  navigateAdmin('papers', { q: '练习', page: '3' })
  navigateAdmin('orders')
  navigateAdmin('papers')
  expect(new URLSearchParams(adminRoute.query).get('page')).toBe('3')
  expect(parseAdminRoute('#bad?x=1').tab).toBe('overview')
})
