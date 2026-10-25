import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import OrderManager from '../components/OrderManager.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { readAdminRoute } from '../navigation'
import * as growth from '../growth'
vi.mock('../growth', async original => ({ ...await original<typeof import('../growth')>(), getOrders: vi.fn(), getOrder: vi.fn(), getPlans: vi.fn() }))

const user = { id: 1, username: 'admin', role: 'admin' }
function order(id: string, username: string) {
  return {
    id, user_id: 'u-' + username, username, nickname: '小助手', plan_name: '月会员', plan_days: 30, amount_fen: 3000,
    status: 'paid', payment_channel: 'wechat', refund: null, created_at: 1761177600,
  } as any
}
function mountOrders() { return mount(OrderManager, { props: { user }, global: { stubs: uiStubs } }) }

beforeEach(() => {
  vi.clearAllMocks()
  history.replaceState(null, '', '/admin/#orders'); readAdminRoute()
  vi.mocked(growth.getOrders).mockResolvedValue({
    items: [order('order-1', 'wx1000000001'), order('order-2', 'wx1000000002')],
    total: 2, has_more: false, summary: { orders: 2, paid_fen: 6000, refunded_fen: 0 },
  })
  vi.mocked(growth.getPlans).mockResolvedValue({ items: [], checkout_enabled: true } as any)
  vi.mocked(growth.getOrder).mockResolvedValue(order('order-1', 'wx1000000001'))
})
afterEach(() => vi.clearAllMocks())

it('list shows the unique account under duplicated nicknames', async () => {
  const wrapper = mountOrders(); await flushPromises()
  const rows = wrapper.findAll('tbody tr')
  expect(rows).toHaveLength(2)
  expect(rows[0]!.text()).toContain('小助手')
  expect(rows[0]!.text()).toContain('账号：wx1000000001')
  expect(rows[1]!.text()).toContain('账号：wx1000000002')
  wrapper.unmount()
})

it('detail dialog shows the unique account as well', async () => {
  const wrapper = mountOrders(); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '查看订单')!.trigger('click')
  await flushPromises()
  const dialog = wrapper.get('[role="dialog"]')
  expect(dialog.text()).toContain('小助手')
  expect(dialog.text()).toContain('账号：wx1000000001')
  wrapper.unmount()
})
