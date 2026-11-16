import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import XhsAccounts from '../components/XhsAccounts.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { adminGroups, adminPageGroups, isXhsContentTab } from '../admin-navigation'

const api = vi.hoisted(() => ({ list: vi.fn(), add: vi.fn(), update: vi.fn(), open: vi.fn(), close: vi.fn() }))
vi.mock('../xhs-accounts', async original => ({ ...await original<typeof import('../xhs-accounts')>(), listXhsAccounts: api.list, addXhsAccount: api.add, updateXhsAccount: api.update, openXhsAccount: api.open, closeXhsAccount: api.close }))
let wrapper: VueWrapper
const account = { id: 'account-a', name: '数学号', note: '原创练习', revision: 2, archived: false, browser_open: false, busy: false }
const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => {
  vi.resetAllMocks()
  window.confirm = vi.fn(() => true)
  api.list.mockResolvedValue({ items: [{ ...account }] }); api.add.mockResolvedValue({ account }); api.open.mockResolvedValue({ account }); api.update.mockResolvedValue({ account }); api.close.mockResolvedValue({ account })
  wrapper = mount(XhsAccounts, { global: { stubs: uiStubs } })
})
afterEach(() => wrapper.unmount())
it('账号管理单独导航，内容阶段保持五个入口', () => {
  expect(adminGroups.find(group=>group.id==='xiaohongshu')!.items.map(item=>item.id)).toEqual(['xhsResearch','xhsAnalytics','xhsAssets','xhsAccounts'])
  expect(adminPageGroups.find(group=>group.id==='xiaohongshu')!.items.some(item=>item.id==='xhsAccounts')).toBe(true)
  expect(isXhsContentTab('xhsAccounts')).toBe(false)
})
it('新增只填写本机名称和备注，保存后可打开正确账号', async () => {
  await flushPromises(); await button('新增小红书账号').trigger('click')
  await wrapper.get('input[aria-label="小红书账号名称"]').setValue('日常号')
  await wrapper.get('textarea[aria-label="小红书账号备注"]').setValue('生活分享')
  await button('保存账号').trigger('click'); await flushPromises()
  expect(api.add).toHaveBeenCalledWith({ name: '日常号', note: '生活分享', request_id: expect.any(String) })
  await button('打开浏览器').trigger('click'); await flushPromises()
  expect(api.open).toHaveBeenCalledWith('account-a')
  expect(wrapper.text()).toContain('核对实际登录账号')
})
it('打开的账号不能归档；关闭需要确认，取消不关闭', async () => {
  api.list.mockResolvedValue({ items: [{ ...account, browser_open: true }] })
  await button('刷新状态').trigger('click'); await flushPromises()
  expect(button('归档账号').attributes('disabled')).toBeDefined()
  vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
  await button('关闭浏览器').trigger('click'); expect(api.close).not.toHaveBeenCalled()
  await button('关闭浏览器').trigger('click'); await flushPromises()
  expect(api.close).toHaveBeenCalledWith('account-a')
})
it('编辑资料使用原版本；归档列表可恢复，实际账号状态不会假报已登录', async () => {
  await flushPromises(); await button('编辑资料').trigger('click')
  await wrapper.get('input[aria-label="小红书账号名称"]').setValue('数学资料号')
  await button('保存账号').trigger('click'); await flushPromises()
  expect(api.update).toHaveBeenCalledWith(expect.objectContaining({ account_id: 'account-a', revision: 2, name: '数学资料号' }))
  api.list.mockResolvedValue({ items: [{ ...account, archived: true }] })
  await button('刷新状态').trigger('click'); await flushPromises()
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await button('恢复账号').trigger('click'); await flushPromises()
  expect(api.update).toHaveBeenLastCalledWith(expect.objectContaining({ archived: false, account_id: 'account-a' }))
})
