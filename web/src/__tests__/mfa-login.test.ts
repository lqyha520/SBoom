import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { uiStubs } from '../../../shared/test/ui-stubs'
import LoginView from '../components/LoginView.vue'
import { useAuthStore } from '../stores/auth'
import * as api from '../api'

afterEach(() => vi.restoreAllMocks())
it('工作台管理员必须完成 MFA 后才进入账号，验证码失败可以重试', async () => {
  setActivePinia(createPinia())
  vi.spyOn(api, 'request').mockResolvedValue({ registration_enabled: false })
  vi.spyOn(api, 'login').mockResolvedValue({ mfa_required: true, challenge: 'challenge-token', username: 'admin' })
  const verify = vi.spyOn(api, 'verifyMfa').mockRejectedValueOnce(new Error('验证码无效')).mockResolvedValue({ id: 1, username: 'admin', role: 'admin' })
  const auth = useAuthStore(), finish = vi.spyOn(auth, 'finishLogin').mockResolvedValue()
  const wrapper = mount(LoginView, { global: { stubs: uiStubs } })
  try {
    await wrapper.get('input[autocomplete="username"]').setValue('admin')
    await wrapper.get('input[autocomplete="current-password"]').setValue('password')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(finish).not.toHaveBeenCalled()
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('验证并登录')
    await wrapper.get('input[autocomplete="one-time-code"]').setValue('123456')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('验证码无效')
    expect(finish).not.toHaveBeenCalled()
    await wrapper.get('input[autocomplete="one-time-code"]').setValue('654321')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(verify).toHaveBeenLastCalledWith('challenge-token', '654321')
    expect(finish).toHaveBeenCalledWith({ id: 1, username: 'admin', role: 'admin' })
  } finally { wrapper.unmount(); auth.$dispose() }
})
