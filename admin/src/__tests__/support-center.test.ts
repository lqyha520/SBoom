import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SupportCenter from '../components/SupportCenter.vue'
import { ApiError } from '../api'
import { readAdminRoute } from '../navigation'
import { uiStubs } from '../../../shared/test/ui-stubs'
import * as experience from '../experience'

vi.mock('../experience', async original => ({ ...await original<typeof import('../experience')>(),
  getFeedback: vi.fn(), getFeedbackDetail: vi.fn(), getSupport: vi.fn(), saveFeedback: vi.fn(),
}))
const user = { id: 1, username: 'admin', role: 'admin' }
const item: experience.Feedback = { id: 'feedback-1', catalog_id: null, paper_title: '', username: 'buyer', nickname: '用户',
  membership: 'regular', is_vip: false, membership_status: 'regular', vip_expires_at: null,
  kind: 'other', body: '需要协助', status: 'pending', reply: '', internal_note: '', revision: 1, updated_at: 1 }
let wrapper: VueWrapper
function button(label: string) { return wrapper.findAll('button').find(value => value.text() === label)! }
beforeEach(() => {
  vi.resetAllMocks()
  history.replaceState(null, '', '/admin/#supportCenter'); readAdminRoute()
  vi.mocked(experience.getFeedback).mockResolvedValue({ items: [{ ...item }], total: 100000, has_more: true })
  vi.mocked(experience.getSupport).mockResolvedValue({ revision: 1, wechat: '', phone: '', email: '', hours: '', benefits: '' })
  vi.mocked(experience.saveFeedback).mockRejectedValueOnce(new ApiError('反馈已经更新', 409)).mockResolvedValue({ ...item, revision: 3 })
  vi.mocked(experience.getFeedbackDetail).mockResolvedValue({ ...item, revision: 2, status: 'resolved', reply: '服务器最新回复', internal_note: '服务器最新备注' })
})
afterEach(() => wrapper?.unmount())
async function conflict() {
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(SupportCenter, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await button('处理与回复').trigger('click')
  const dialog = wrapper.get('[role="dialog"]')
  await dialog.get('select').setValue('processing')
  await dialog.findAll('textarea')[0]!.setValue('我的回复草稿')
  await dialog.findAll('textarea')[1]!.setValue('我的内部备注')
  await wrapper.get('#feedback-reply').trigger('submit'); await flushPromises()
  expect(button('载入最新并保留我的修改')).toBeDefined()
}
it('冲突恢复直接按 ID 取详情，大列表不扫描分页，本地状态回复和备注均保留', async () => {
  await conflict()
  vi.mocked(experience.getFeedbackDetail).mockResolvedValueOnce({ ...item, revision: 2, status: 'resolved', reply: '服务器最新回复', internal_note: '服务器最新备注',
    membership: 'vip', is_vip: true, membership_status: 'active', vip_expires_at: null })
  await button('载入最新并保留我的修改').trigger('click'); await flushPromises()
  expect(experience.getFeedbackDetail).toHaveBeenCalledExactlyOnceWith('feedback-1')
  expect(experience.getFeedback).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('服务器最新回复')
  expect(wrapper.text()).toContain('服务器最新备注')
  const dialog = wrapper.get('[role="dialog"]')
  expect(dialog.get('.feedback-identity').text()).toContain('VIP 会员')
  expect((dialog.get('select').element as HTMLSelectElement).value).toBe('processing')
  expect((dialog.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe('我的回复草稿')
  expect((dialog.findAll('textarea')[1]!.element as HTMLTextAreaElement).value).toBe('我的内部备注')
  await wrapper.get('#feedback-reply').trigger('submit'); await flushPromises()
  expect(experience.saveFeedback).toHaveBeenLastCalledWith(1, expect.objectContaining({ revision: 2, status: 'processing', reply: '我的回复草稿', internal_note: '我的内部备注' }))
})
it.each([
  { membership: 'regular', is_vip: false, membership_status: 'regular', label: '普通用户' },
  { membership: 'vip', is_vip: true, membership_status: 'active', label: 'VIP 会员' },
  { membership: 'vip', is_vip: false, membership_status: 'expired', label: '普通用户' },
] as const)('列表和回复弹窗按服务端身份显示 $membership_status', async identity => {
  vi.mocked(experience.getFeedback).mockResolvedValueOnce({ items: [{ ...item, ...identity, kind: 'membership' }], total: 1, has_more: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(SupportCenter, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  const row = wrapper.get('tbody tr')
  expect(row.findAll('td')[1]!.text()).toContain(identity.label)
  expect(row.text().includes('会员已到期')).toBe(identity.membership_status === 'expired')
  await button('处理与回复').trigger('click')
  const detail = wrapper.get('.feedback-identity')
  expect(detail.text()).toContain(identity.label)
  expect(detail.text().includes('会员已到期')).toBe(identity.membership_status === 'expired')
})
it.each([404, 503])('详情返回 %i 时保留草稿和恢复入口，允许单独重试', async status => {
  await conflict()
  vi.mocked(experience.getFeedbackDetail).mockRejectedValueOnce(new ApiError(status === 404 ? '反馈记录不存在' : '详情暂不可用', status))
  await button('载入最新并保留我的修改').trigger('click'); await flushPromises()
  expect((wrapper.get('[role="dialog"] textarea').element as HTMLTextAreaElement).value).toBe('我的回复草稿')
  expect(button('载入最新并保留我的修改').attributes('disabled')).toBeUndefined()
  await button('载入最新并保留我的修改').trigger('click'); await flushPromises()
  expect(experience.getFeedbackDetail).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).toContain('服务器最新回复')
})
