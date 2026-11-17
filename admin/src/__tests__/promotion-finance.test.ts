import { expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { financeGrant, financeUser } from '../promotion-finance'
import { request } from '../api'
import type { UserInfo } from '../api'
import { feeDrafts, sharedFeeValues, personalFeeValues, type Statement } from '../settlements'
import SettlementEvidence from '../components/SettlementEvidence.vue'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
it('财务授权分别控制核对、审核、付款，不扩大其他阶段权限', () => {
  const user: UserInfo = { id: 3, username: 'finance', role: 'admin', is_super_admin: false, admin_permissions: { settlementCosts: ['view', 'run'], settlements: ['view'] } }
  expect(financeUser(user)).toBe(true)
  expect(financeGrant(user, 'Costs')).toBe(true)
  expect(financeGrant(user, 'Review')).toBe(false)
  expect(financeGrant(user, 'Payout')).toBe(false)
  expect(financeUser({ ...user, admin_permissions: { settlements: ['view', 'create'] } })).toBe(false)
})
it('审核检查只应用审核阻塞，付款检查应用付款阻塞', async () => {
  const statement: Statement = { id: 'stage-1', beneficiary: 'admin:1', beneficiary_name: 'one', status: 'draft', revision: 1, gross_fen: 100, adjustment_fen: 0, personal_fen: 0, tax_fen: 0, net_fen: 0, reason: '', receipt: '', created_at: 100, snapshot: { items: [], adjustments: [] }, review: null }
  vi.mocked(request).mockResolvedValue({ statement, attachments: [], bill_differences: [], operation_issues: [{ order_id: 'stage-1', purpose: 'payment', reasons: ['审核人不能登记付款'] }] })
  const options = { global: { stubs: { UButton: { props: ['label'], template: '<button>{{ label }}</button>' }, UAlert: { props: ['title'], template: '<p>{{ title }}</p>' }, UFormField: true } } }
  let wrapper = mount(SettlementEvidence, { ...options, props: { actor: 1, item: statement, finance: true, purpose: 'review' } })
  await flushPromises()
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([false])
  expect(wrapper.text()).not.toContain('审核人不能登记付款')
  wrapper.unmount()
  wrapper = mount(SettlementEvidence, { ...options, props: { actor: 1, item: statement, finance: true, purpose: 'payment' } })
  await flushPromises()
  expect(wrapper.emitted('blocked')?.slice(-1)[0]).toEqual([true])
  expect(wrapper.text()).toContain('审核人不能登记付款')
  wrapper.unmount()
})

it('核费草稿与金额或比例提交均保留实际凭据关联编号', () => {
  const fixed = feeDrafts([{ name: '广告费', amount_fen: 100, source_ref: 'fp001/广告' }])
  expect(sharedFeeValues(fixed)[0]).toMatchObject({ amount_fen: 100, source_ref: 'fp001/广告' })
  const percent = feeDrafts([{ name: '个人服务费', mode: 'percent', rate_bps: 500, basis: 'after_channel', source_ref: 'fp001/服务' }])
  percent[0]!.basis = 'reward_gross'
  expect(personalFeeValues(percent)[0]).toMatchObject({ rate_bps: 500, source_ref: 'fp001/服务' })
})
