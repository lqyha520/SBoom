import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import OrderManager from '../components/OrderManager.vue'
import Reconciliations from '../components/Reconciliations.vue'
import { readAdminRoute } from '../navigation'
import { uiStubs } from '../../../shared/test/ui-stubs'
import * as growth from '../growth'

vi.mock('../growth', async original => ({ ...await original<typeof import('../growth')>(),
  getOrders: vi.fn(), getOrder: vi.fn(), getPlans: vi.fn(), exportOrders: vi.fn(), syncOrder: vi.fn(),
  getReconciliations: vi.fn(), getReconciliation: vi.fn(), reconcile: vi.fn(), reviewRefund: vi.fn(), cancelOrder: vi.fn(),
}))

type Plans = Awaited<ReturnType<typeof growth.getPlans>>
const user = { id: 1, username: 'admin', role: 'admin' }
function plans(wechat: boolean, virtual: boolean, virtualEnabled = virtual): Plans {
  return { items: [], checkout_enabled: virtualEnabled ? virtual : wechat, checkout_channel: virtualEnabled ? 'virtual' : 'wechat', ios_enabled: false,
    configuration: { enabled: wechat, ready: wechat, missing: [], ios_enabled: false, payment_callback: '', refund_callback: '' },
    virtual_configuration: { enabled: virtualEnabled, ready: virtual, missing: [], env: 0, sandbox: false, offer_id: '', ios_enabled: false, mode: '' },
  }
}
function order(channel: growth.PaymentChannel = 'wechat'): growth.Order {
  return { id: 'order-1', user_id: 'buyer-1', username: 'buyer', nickname: '测试用户', plan_name: '月会员', plan_days: 30,
    amount_fen: 3000, status: 'pending', payment_channel: channel, virtual_env: 0, virtual_offer_id: '', virtual_product_id: '',
    virtual_order_id: '', virtual_order_type: 0, device_platform: 'android', delivered_at: null, revision: 1,
    created_at: 1761177600, paid_at: null, expires_at: 1761178500, transaction_id: null, refund: null,
  }
}
const record: growth.Reconciliation = { id: 'recon-1', bill_date: '2026-10-20', status: 'complete', error: '', created_at: 1792540800,
  summary: { wechat_paid_fen: 3000, wechat_refunded_fen: 0, local_paid_fen: 3000, local_refunded_fen: 0, differences: 0 } }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (cause: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
let wrapper: VueWrapper
function button(label: string) { return wrapper.findAll('button').find(item => item.text() === label)! }
function mountOrders() { wrapper = mount(OrderManager, { props: { user }, global: { stubs: uiStubs } }); return wrapper }
function mountReconciliations() {
  history.replaceState(null, '', '/admin/#reconciliations'); readAdminRoute()
  wrapper = mount(Reconciliations, { props: { user }, global: { stubs: uiStubs } })
}
beforeEach(() => {
  vi.resetAllMocks()
  history.replaceState(null, '', '/admin/#orders'); readAdminRoute()
  vi.mocked(growth.getPlans).mockResolvedValue(plans(true, false))
  vi.mocked(growth.getOrders).mockResolvedValue({ items: [order()], total: 1, has_more: false, summary: { orders: 1, paid_fen: 3000, refunded_fen: 0 } })
  vi.mocked(growth.getOrder).mockResolvedValue(order())
  vi.mocked(growth.exportOrders).mockResolvedValue(undefined)
  vi.mocked(growth.getReconciliations).mockResolvedValue({ items: [record], total: 1, has_more: false })
  vi.mocked(growth.getReconciliation).mockResolvedValue(record)
})
afterEach(() => wrapper?.unmount())

it('支付配置慢时订单及金额先展示，查询和导出不等待配置', async () => {
  const pending = deferred<Plans>()
  vi.mocked(growth.getPlans).mockReturnValue(pending.promise)
  mountOrders(); await flushPromises()
  expect(wrapper.text()).toContain('月会员')
  expect(wrapper.text()).toContain('¥30.00')
  expect(button('查询订单').attributes('disabled')).toBeUndefined()
  await button('导出 CSV').trigger('click'); await flushPromises()
  expect(growth.exportOrders).toHaveBeenCalledOnce()
  pending.resolve(plans(true, false)); await flushPromises()
})

it('配置失败仍可查看订单，单独重试配置不重取列表', async () => {
  vi.mocked(growth.getPlans).mockRejectedValueOnce(new Error('配置暂不可用')).mockResolvedValueOnce(plans(true, false))
  mountOrders(); await flushPromises()
  expect(wrapper.text()).toContain('月会员')
  expect(wrapper.text()).toContain('支付配置读取失败')
  await button('查看订单').trigger('click'); await flushPromises()
  expect(button('查询微信状态').attributes('disabled')).toBeDefined()
  await button('刷新支付配置').trigger('click'); await flushPromises()
  expect(button('查询微信状态').attributes('disabled')).toBeUndefined()
  expect(wrapper.text()).not.toContain('支付配置读取失败')
  expect(growth.getOrders).toHaveBeenCalledOnce()
})

it.each(['wechat', 'virtual'] as const)('配置失败不阻塞可本地关闭的 %s 未付款订单', async channel => {
  const item = order(channel)
  item.status = 'created'
  vi.mocked(growth.getPlans).mockRejectedValue(new Error('配置暂不可用'))
  vi.mocked(growth.getOrder).mockResolvedValue(item)
  vi.mocked(growth.cancelOrder).mockResolvedValue({ ...item, status: 'closed' })
  mountOrders(); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  await wrapper.get('[role="dialog"] input[type="checkbox"]').setValue(true)
  await button('关闭未付款订单').trigger('click'); await flushPromises()
  expect(growth.cancelOrder).toHaveBeenCalledExactlyOnceWith(1, item.id)
  expect(wrapper.text()).toContain('已核对并关闭未付款订单')
})

it('刷新配置期间立即撤回旧能力，失败后不沿用旧的就绪状态', async () => {
  mountOrders(); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  const pending = deferred<Plans>()
  vi.mocked(growth.getPlans).mockReturnValueOnce(pending.promise)
  await button('刷新支付配置').trigger('click')
  expect(button('查询微信状态').attributes('disabled')).toBeDefined()
  pending.reject(new Error('配置刷新失败')); await flushPromises()
  expect(button('查询微信状态').attributes('disabled')).toBeDefined()
})

it.each(['wechat', 'virtual'] as const)('订单查询按自身 %s 渠道判断能力', async channel => {
  vi.mocked(growth.getPlans).mockResolvedValue(plans(false, true))
  vi.mocked(growth.getOrder).mockResolvedValue(order(channel))
  mountOrders(); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  expect(button('查询微信状态').attributes('disabled') === undefined).toBe(channel === 'virtual')
})

it('当前虚拟支付不可用时，历史微信订单仍按微信配置提供查询', async () => {
  vi.mocked(growth.getPlans).mockResolvedValue(plans(true, false, true))
  mountOrders(); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  expect(button('查询微信状态').attributes('disabled')).toBeUndefined()
})

it('退款批准不能使用其他支付渠道的就绪状态，拒绝仍可保存', async () => {
  const item = order()
  item.status = 'paid'
  item.refund = { id: 'refund-1', reason: '申请退款', reply: '', status: 'requested', revision: 1, created_at: 1, updated_at: 1, completed_at: null }
  vi.mocked(growth.getPlans).mockResolvedValue(plans(false, true))
  vi.mocked(growth.getOrder).mockResolvedValue(item)
  mountOrders(); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  await wrapper.get('textarea').setValue('已核对原因')
  expect(button('保存审核结果').attributes('disabled')).toBeUndefined()
  await wrapper.get('[role="dialog"] select').setValue('approve')
  await wrapper.get('[role="dialog"] input[type="checkbox"]').setValue(true)
  expect(button('确认发起全额退款').attributes('disabled')).toBeDefined()
  await wrapper.get('#refund-review').trigger('submit'); await flushPromises()
  expect(growth.reviewRefund).not.toHaveBeenCalled()
})

it('离页前的配置迟到响应不能覆盖返回页面后取得的新配置', async () => {
  const pending = deferred<Plans>(), visible = ref(true)
  vi.mocked(growth.getPlans).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(plans(false, false))
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => visible.value ? h(OrderManager, { user }) : null) }), { global: { stubs: uiStubs } })
  await flushPromises()
  visible.value = false; await flushPromises()
  visible.value = true; await flushPromises()
  pending.resolve(plans(true, false)); await flushPromises()
  await button('查看订单').trigger('click'); await flushPromises()
  expect(growth.getPlans).toHaveBeenCalledTimes(2)
  expect(button('查询微信状态').attributes('disabled')).toBeDefined()
})

it('对账记录和详情不等待慢配置，失败时保留记录并支持重试', async () => {
  const pending = deferred<Plans>()
  vi.mocked(growth.getPlans).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(plans(true, false))
  mountReconciliations(); await flushPromises()
  expect(wrapper.text()).toContain('2026-10-20')
  await button('查看差异').trigger('click'); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  pending.reject(new Error('配置暂不可用')); await flushPromises()
  expect(wrapper.text()).toContain('支付配置读取失败')
  await button('刷新支付配置').trigger('click'); await flushPromises()
  expect(button('下载并核对账单').attributes('disabled')).toBeUndefined()
  expect(growth.getReconciliations).toHaveBeenCalledOnce()
})

it('仅虚拟支付就绪时不允许下载微信商户账单，直接提交也不发请求', async () => {
  vi.mocked(growth.getPlans).mockResolvedValue(plans(false, true))
  mountReconciliations(); await flushPromises()
  expect(button('下载并核对账单').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('不包含虚拟支付订单')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(growth.reconcile).not.toHaveBeenCalled()
})

it('虚拟支付故障不影响已就绪的微信商户对账', async () => {
  vi.mocked(growth.getPlans).mockResolvedValue(plans(true, false, true))
  mountReconciliations(); await flushPromises()
  expect(button('下载并核对账单').attributes('disabled')).toBeUndefined()
})
