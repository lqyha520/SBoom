import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { request } from '../api'
import { navigateAdmin } from '../navigation'
import ReferralManager from '../components/ReferralManager.vue'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
vi.mock('../../../shared/download', () => ({ downloadBlob: vi.fn() }))
const api = vi.mocked(request)
const global = { stubs: {
  UButton: { props: ['label', 'disabled'], template: '<button :disabled="disabled">{{ label }}<slot /></button>' },
  UInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">' },
  USelect: { props: ['modelValue', 'items'], emits: ['update:modelValue'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="item in items" :value="item.value">{{ item.label }}</option></select>' },
  UFormField: { template: '<label><slot /></label>' },
  UAlert: { props: ['title'], template: '<p role="alert">{{ title }}</p>' },
  UModal: true, UIcon: true, UPagination: true, PromotionTabs: true,
  ReferralCampaigns: true, ReferralConversion: true, ReferralRules: true,
  ReferralAcquisition: true, ReferralQuality: true, ReferralComparison: true,
} }
beforeEach(() => { api.mockReset(); navigateAdmin('referrals', { section: 'records' }) })
it('查询前阻止按草稿筛选导出，查询后导出与表格使用同一范围', async () => {
  api.mockImplementation(async path => {
    if (path.includes('/export/users')) return new Blob(['csv']) as never
    if (path.includes('/admins')) return { items: [] } as never
    if (path.includes('/users?')) return { items: [{ id: 'old-user', username: 'old-user', nickname: '查询结果', created_at: 1, referral: { source: 'legacy' } }], total: 1 } as never
    if (path.includes('/summary?')) return { registrations: 1, orders: 0, paying_users: 0, paid_fen: 0, refunded_fen: 0, net_fen: 0 } as never
    throw new Error(path)
  })
  const wrapper = mount(ReferralManager, { props: { user: { id: 1, username: 'admin', role: 'admin', is_super_admin: true } }, global })
  await flushPromises()
  await wrapper.get('input[aria-label="搜索推广明细"]').setValue('new-filter')
  await flushPromises()
  const button = wrapper.findAll('button').find(item => item.text() === '导出 CSV')!
  expect((button.element as HTMLButtonElement).disabled).toBe(true)
  expect(wrapper.text()).toContain('当前结果仍按上次查询范围展示')
  expect(api.mock.calls.some(([path]) => path.includes('/export/users'))).toBe(false)
  await wrapper.get('.promotion-record-toolbar').trigger('submit')
  await flushPromises()
  expect((button.element as HTMLButtonElement).disabled).toBe(false)
  await button.trigger('click'); await flushPromises()
  expect(api.mock.calls.find(([path]) => path.includes('/export/users'))?.[0]).toContain('q=new-filter')
  expect(api.mock.calls.filter(([path]) => path.includes('/users?')).slice(-1)[0]?.[0]).toContain('q=new-filter')
  wrapper.unmount()
})
