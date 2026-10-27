import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import MiniUsers from '../components/MiniUsers.vue'
import { readAdminRoute } from '../navigation'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { miniUsers, type MiniUser } from '../mini'

vi.mock('../mini', async original => ({ ...await original<typeof import('../mini')>(), miniUsers: vi.fn() }))
vi.mock('../components/MemberTools.vue', () => ({ default: { render: () => null } }))
let wrapper: VueWrapper
const user = { id: 1, username: 'admin', role: 'admin' }
const buyer: MiniUser = { id: 'buyer', username: 'buyer', avatar: '', has_password: true, membership: 'regular', is_vip: false,
  membership_status: 'regular', vip_expires_at: null, is_active: true, revision: 1, created_at: 1, updated_at: 1, login_method: 'password' }
beforeEach(() => {
  vi.resetAllMocks()
  history.replaceState(null, '', '/admin/#miniUsers?page=40'); readAdminRoute()
})
afterEach(() => wrapper?.unmount())
function show() {
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(MiniUsers, { user })) }), { global: { stubs: uiStubs } })
}
it.each([0, 21])('失效页码按总数 %i 直接跳到有效末页，不逐页请求', async total => {
  vi.mocked(miniUsers).mockImplementation(async (_q, _membership, offset) => ({ items: offset < total ? [buyer] : [], total, has_more: false }))
  show()
  for (let i = 0; i < 5; i++) await flushPromises()
  const offsets = vi.mocked(miniUsers).mock.calls.map(call => call[2])
  const expected = total ? 20 : 0
  expect(offsets).toContain(780)
  expect(offsets).toContain(expected)
  expect(offsets.every(offset => offset === 780 || offset === expected)).toBe(true)
  expect(offsets.length).toBeLessThanOrEqual(3)
  expect(new URLSearchParams(location.hash.split('?')[1]).get('page')).toBe(total ? '2' : null)
})
it('有效页码不会被回退', async () => {
  vi.mocked(miniUsers).mockResolvedValue({ items: [buyer], total: 800, has_more: false })
  show(); await flushPromises()
  expect(vi.mocked(miniUsers).mock.calls.every(call => call[2] === 780)).toBe(true)
  expect(location.hash).toContain('page=40')
})
it('超大 URL 页码先限制到接口可接受范围，再按真实总数回退', async () => {
  history.replaceState(null, '', '/admin/#miniUsers?page=100000'); readAdminRoute()
  vi.mocked(miniUsers).mockImplementation(async (_q, _membership, offset) => {
    if (offset > 100000) throw new Error('offset 超过接口上限')
    return { items: offset === 0 ? [buyer] : [], total: 1, has_more: false }
  })
  show()
  for (let i = 0; i < 5; i++) await flushPromises()
  const offsets = vi.mocked(miniUsers).mock.calls.map(call => call[2])
  expect(offsets).toContain(100000)
  expect(offsets).toContain(0)
  expect(offsets.every(offset => offset === 100000 || offset === 0)).toBe(true)
  expect(wrapper.text()).toContain('buyer')
  expect(wrapper.text()).not.toContain('offset 超过接口上限')
})
