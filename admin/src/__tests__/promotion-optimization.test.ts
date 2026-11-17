import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { request } from '../api'
import { referenceRewardLabel } from '../referrals'
import { readBudgetDraft, storeBudgetDraft } from '../promotion-budget-draft'
import ReferralCampaigns from '../components/ReferralCampaigns.vue'
import SettlementEvidence from '../components/SettlementEvidence.vue'
import type { Statement } from '../settlements'

vi.mock('../api', async importOriginal => ({ ...await importOriginal<typeof import('../api')>(), request: vi.fn() }))
const api = vi.mocked(request)
const global = { stubs: {
  UButton: { props: ['label', 'disabled'], template: '<button :disabled="disabled">{{ label }}<slot /></button>' },
  UAlert: { props: ['title'], template: '<p role="alert">{{ title }}</p>' },
  UFormField: { props: ['label'], template: '<label :data-field="label"><slot /></label>' },
  UInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">' },
  USelect: { props: ['modelValue', 'items'], emits: ['update:modelValue'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="item in items" :key="item.value" :value="item.value">{{ item.label }}</option></select>' },
  UPagination: true, UIcon: true, UModal: true, ReferralMaterials: true, ReferralCampaignDetail: true,
} }
beforeEach(() => { api.mockReset(); sessionStorage.clear() })

it('参考奖励区分全部未知、已知零金额、部分未知和已知金额', () => {
  expect(referenceRewardLabel({ reward_reference_fen: 0, reward_unknown: 2, reward_known: 0 })).toBe('待核对（2 笔）')
  expect(referenceRewardLabel({ reward_reference_fen: 0, reward_unknown: 2, reward_known: 1 })).toBe('已知小计 ¥0.00；另有 2 笔待核对')
  expect(referenceRewardLabel({ reward_reference_fen: 125, reward_unknown: 1, reward_known: 2 })).toBe('已知小计 ¥1.25；另有 1 笔待核对')
  expect(referenceRewardLabel({ reward_reference_fen: 0, reward_unknown: 0 })).toBe('¥0.00')
})

it('筛选、翻页和管理员切换保留预算草稿，保存使用编辑起始版本', async () => {
  const writes: { owner: string; revision: number; budget_fen: number }[] = []
  let revision = 1
  api.mockImplementation(async (path, init) => {
    if (path.includes('/campaigns?')) return { items: [], total: 42, page: 1 } as never
    if (path.includes('/budget/')) {
      if (init?.method === 'PUT') writes.push({ owner: path.split('/').pop()!, ...JSON.parse(String(init.body)) })
      return { revision, budget_fen: 1000, used_fen: 100, unknown: 0, reached: false } as never
    }
    throw new Error('unexpected request ' + path)
  })
  const wrapper = mount(ReferralCampaigns, { props: { user: { id: 1, username: 'admin', role: 'admin', is_super_admin: true }, accounts: [{ id: 1, username: 'one', is_active: 1 }, { id: 2, username: 'two', is_active: 1 }] }, global })
  await flushPromises()
  const budget = () => wrapper.get('[data-field="管理员月度预算（元，留空关闭预警）"] input')
  await budget().setValue('88.00')
  revision = 2
  await wrapper.get('form[aria-label="活动筛选"]').trigger('submit'); await flushPromises()
  expect((budget().element as HTMLInputElement).value).toBe('88.00')
  wrapper.findComponent({ name: 'UPagination' }).vm.$emit('update:page', 2); await flushPromises()
  expect((budget().element as HTMLInputElement).value).toBe('88.00')
  await wrapper.get('select[aria-label="活动所属管理员"]').setValue('2'); await flushPromises()
  expect((budget().element as HTMLInputElement).value).toBe('10.00')
  await budget().setValue('66.00')
  await wrapper.get('select[aria-label="活动所属管理员"]').setValue('1'); await flushPromises()
  expect((budget().element as HTMLInputElement).value).toBe('88.00')
  await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises()
  expect(writes).toEqual([{ owner: '1', revision: 1, budget_fen: 8800 }])
  wrapper.unmount()
})

it('付款面板展示最新账单差异并阻止付款，资料补齐后重新核对', async () => {
  const statement: Statement = { id: 'statement-1', beneficiary: 'admin:1', beneficiary_name: 'admin', revision: 1, status: 'approved',
    gross_fen: 100, adjustment_fen: 0, personal_fen: 0, tax_fen: 0, net_fen: 100, reason: '', receipt: '', created_at: 1794300000,
    snapshot: { items: [], adjustments: [] }, review: null }
  api.mockResolvedValueOnce({ statement, attachments: [], timeline: [], bill_differences: [{ order_id: 'order-1', reasons: ['交易号不一致'] }] })
  const wrapper = mount(SettlementEvidence, { props: { actor: 1, item: statement, finance: true }, global })
  await flushPromises()
  expect(wrapper.text()).toContain('order-1：交易号不一致')
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([true])
  const complete = { ...statement, revision: 2, snapshot: { ...statement.snapshot, payee: { name: '收款人', method: 'bank' as const, account: '****1234', bank: '测试银行', revision: 1 } } }
  api.mockResolvedValueOnce({ statement: complete, attachments: [], timeline: [], bill_differences: [] })
  await wrapper.setProps({ item: complete }); await flushPromises()
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([false])
  wrapper.unmount()
})

it('刷新后恢复预算输入与原版本，保存后清除备份', async () => {
  let revision = 1, amount = 1000
  const writes: { revision: number; budget_fen: number }[] = []
  api.mockImplementation(async (path, init) => {
    if (path.includes('/campaigns?')) return { items: [], total: 0 } as never
    if (init?.method === 'PUT') { const body = JSON.parse(String(init.body)); writes.push(body); amount = body.budget_fen; revision++ }
    return { revision, budget_fen: amount, used_fen: 0, unknown: 0, reached: false } as never
  })
  const options = { props: { user: { id: 1, username: 'admin', role: 'admin', is_super_admin: true }, accounts: [{ id: 1, username: 'one', is_active: 1 }] }, global }
  let wrapper = mount(ReferralCampaigns, options)
  await flushPromises()
  await wrapper.get('[data-field="管理员月度预算（元，留空关闭预警）"] input').setValue('88.00')
  wrapper.unmount()
  revision = 2
  wrapper = mount(ReferralCampaigns, options); await flushPromises()
  expect((wrapper.get('[data-field="管理员月度预算（元，留空关闭预警）"] input').element as HTMLInputElement).value).toBe('88.00')
  expect(wrapper.text()).toContain('已恢复本标签页尚未保存的预算草稿')
  expect(wrapper.text()).toContain('后台预算已更新')
  await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises()
  expect(writes).toEqual([{ revision: 1, budget_fen: 8800 }])
  expect(readBudgetDraft(1, '1')).toBeNull()
  wrapper.unmount()
})

it('预算备份按登录账号及所属管理员隔离，并忽略损坏内容', () => {
  const draft = { revision: 1, value: '88.00', saved: '10.00' }
  storeBudgetDraft(1, '2', draft)
  expect(readBudgetDraft(1, '2')).toEqual(draft)
  expect(readBudgetDraft(2, '2')).toBeNull()
  expect(readBudgetDraft(1, '1')).toBeNull()
  const name = sessionStorage.key(0)!
  sessionStorage.setItem(name, 'invalid json')
  expect(readBudgetDraft(1, '2')).toBeNull()
  sessionStorage.setItem(name, JSON.stringify({ ...draft, version: 1, revision: -1 }))
  expect(readBudgetDraft(1, '2')).toBeNull()
})

it('预算备份写入失败仍保留输入并提醒先保存', async () => {
  api.mockResolvedValue({ revision: 1, budget_fen: 1000, used_fen: 0, unknown: 0, reached: false, items: [], total: 0 })
  const wrapper = mount(ReferralCampaigns, { props: { user: { id: 1, username: 'admin', role: 'admin', is_super_admin: true }, accounts: [] }, global })
  await flushPromises()
  vi.spyOn(sessionStorage, 'setItem').mockImplementation(() => { throw new Error('quota exceeded') })
  const input = wrapper.get('[data-field="管理员月度预算（元，留空关闭预警）"] input')
  await input.setValue('99.00')
  expect((input.element as HTMLInputElement).value).toBe('99.00')
  expect(wrapper.text()).toContain('预算草稿暂无法保存在本标签页')
  wrapper.unmount()
})

it('审核预检拦截差异，核对通过后无需收款账号即可审核', async () => {
  const statement: Statement = { id: 'draft-1', beneficiary: 'admin:1', beneficiary_name: 'admin', revision: 1, status: 'draft',
    gross_fen: 100, adjustment_fen: 0, personal_fen: 0, tax_fen: null, net_fen: null, reason: '', receipt: '', created_at: 1794300000,
    snapshot: { items: [], adjustments: [] }, review: null }
  api.mockResolvedValueOnce({ statement, attachments: [], bill_differences: [{ order_id: 'order-1', reasons: ['账单差异未完整留存'] }] })
  const wrapper = mount(SettlementEvidence, { props: { actor: 1, item: statement, finance: true, purpose: 'review' }, global })
  await flushPromises()
  expect(wrapper.text()).toContain('审核前账单检查')
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([true])
  api.mockRejectedValueOnce(new Error('账单读取失败'))
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([true])
  expect(wrapper.text()).toContain('账单读取失败')
  api.mockResolvedValueOnce({ statement, attachments: [], bill_differences: [] })
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([false])
  wrapper.unmount()
})
