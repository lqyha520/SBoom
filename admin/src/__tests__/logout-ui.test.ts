import { expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import Dashboard from '../components/Dashboard.vue'
import * as api from '../api'
import { uiStubs } from '../../../shared/test/ui-stubs'

vi.mock('../components/OverviewPage.vue', () => ({ __esModule: true, default: { name: 'OverviewStub', render: () => null } }))

it('后台退出失败显示错误并允许重试，成功后才通知外壳退出', async () => {
  const logout = vi.spyOn(api, 'logout').mockRejectedValueOnce(new Error('网络异常，请重试')).mockResolvedValue(undefined)
  const wrapper = mount(Dashboard, {
    props: { user: { id: 1, username: 'admin', role: 'admin' } },
    global: { stubs: { ...uiStubs,
      UDropdownMenu: defineComponent({ props: ['items'], setup: props => () => h('div', props.items.map((item: { label: string; onSelect?: () => void; disabled?: boolean }) => h('button', { onClick: item.onSelect, disabled: item.disabled }, item.label))) }),
    } },
  })
  try {
    const button = () => wrapper.findAll('button').find(value => value.text() === '退出登录')!
    await button().trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('网络异常，请重试')
    expect(wrapper.emitted('logout')).toBeUndefined()
    expect(button().attributes('disabled')).toBeUndefined()
    await button().trigger('click'); await flushPromises()
    expect(wrapper.emitted('logout')).toEqual([[]])
    expect(logout).toHaveBeenCalledTimes(2)
  } finally { wrapper.unmount() }
})
