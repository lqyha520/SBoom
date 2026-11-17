import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import XhsPublicationAccount from '../components/XhsPublicationAccount.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'

const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../xhs-accounts', () => ({ listXhsAccounts: api.list }))
let wrapper: VueWrapper
const account = { id: 'account-a', name: '数学号', archived: false }
beforeEach(() => { vi.resetAllMocks(); api.list.mockResolvedValue({ items: [account, { id:'archived',name:'旧账号',archived:true }] }) })
afterEach(() => wrapper.unmount())
const setup = (current = { id: '', name: '' }) => { wrapper = mount(XhsPublicationAccount, { props: { current }, global: { stubs: uiStubs } }) }

it('直接选择已保存账号，同时关联编号和昵称，不需要再点击应用', async () => {
  setup(); await flushPromises()
  expect(wrapper.findAll('option').map(option => option.text())).not.toContain('旧账号')
  await wrapper.get('select').setValue('account-a')
  expect(wrapper.emitted('apply')?.slice(-1)[0]).toEqual([{ id: 'account-a', name: '数学号' }])
  await wrapper.setProps({ current: { id:'account-a',name:'数学号' } })
  expect(wrapper.find('input[aria-label="发布账号"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('已选择：数学号')
})

it('账号服务加载期间仍能操作下拉框或手动填写昵称', async () => {
  api.list.mockReturnValue(new Promise(() => {}))
  setup()
  expect(wrapper.get('select').attributes('disabled')).toBeUndefined()
  await wrapper.get('input[aria-label="发布账号"]').setValue('日常号')
  expect(wrapper.emitted('apply')?.slice(-1)[0]).toEqual([{ id: '', name: '日常号' }])
})

it('账号加载失败保留原账号，手动填写是显式切换', async () => {
  api.list.mockRejectedValue(new Error('本机服务不可用'))
  setup({ id:'account-a',name:'数学号' }); await flushPromises()
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('account-a')
  expect(wrapper.get('select').attributes('disabled')).toBeUndefined()
  expect(wrapper.text()).toContain('账号列表暂时无法加载')
  expect(wrapper.emitted('apply')).toBeUndefined()
  await wrapper.get('select').setValue('__manual__')
  expect(wrapper.emitted('apply')?.slice(-1)[0]).toEqual([{ id:'',name:'数学号' }])
})
