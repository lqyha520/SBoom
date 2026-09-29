import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Cards from '../components/MembershipCards.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { readAdminRoute } from '../navigation'
import * as growth from '../growth'
vi.mock('../growth', async original => ({ ...await original<typeof import('../growth')>(), getCards: vi.fn(), createCards: vi.fn(), disableCard: vi.fn() }))
beforeEach(() => {
  vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
  vi.clearAllMocks()
  history.replaceState(null, '', '/admin/#membershipCards'); readAdminRoute()
  vi.mocked(growth.getCards).mockResolvedValue({ items: [{ id: 'card', code_hint: 'ABCD', days: 30, status: 'active', expires_at: null } as any], total: 80, has_more: true })
})
afterEach(() => vi.unstubAllGlobals())
function mountCards() { return mount(Cards, { props: { user: { id: 1, username: 'admin', role: 'admin' } }, global: { stubs: uiStubs } }) }
it('filters and pagination reload data and status change resets the page', async () => {
  const wrapper = mountCards(); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '下一页')!.trigger('click'); await flushPromises()
  expect(growth.getCards).toHaveBeenLastCalledWith('', 50, '')
  await wrapper.get('[aria-label="卡密状态"]').setValue('disabled'); await flushPromises()
  expect(growth.getCards).toHaveBeenLastCalledWith('disabled', 0, '')
  await wrapper.get('[aria-label="卡密尾号"]').setValue('abcd'); await flushPromises()
  expect(growth.getCards).toHaveBeenLastCalledWith('disabled', 0, 'abcd')
  expect(location.hash).toContain('status=disabled')
  expect(location.hash).toContain('q=abcd')
  wrapper.unmount()
})
it('expiry uses the end of the Beijing date and cancelling disable makes no write', async () => {
  vi.mocked(growth.createCards).mockResolvedValue({ items: [{ code: 'LC-SECRET', days: 30, expires_at: null }] })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const wrapper = mountCards(); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '作废')!.trigger('click')
  expect(growth.disableCard).not.toHaveBeenCalled()
  await wrapper.get('input[type="date"]').setValue('2099-10-01')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(growth.createCards).toHaveBeenCalledWith(1, 30, 1, Date.parse('2099-10-01T23:59:59+08:00') / 1000)
  expect(wrapper.get('textarea').element.value).toContain('LC-SECRET')
  wrapper.unmount(); confirm.mockRestore()
})
