import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LoginForm from '../components/LoginForm.vue'
import * as api from '../api'
import { uiStubs } from '../../../shared/test/ui-stubs'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); api.bindAdminAccount(null) })

it('密码阶段结束后清空密码仍可提交动态验证码，失败可重试', async () => {
  vi.spyOn(api, 'login').mockResolvedValue({ mfa_required: true, challenge: 'challenge-token', username: 'admin' })
  const verify = vi.spyOn(api, 'verifyMfa').mockRejectedValueOnce(new Error('验证码无效')).mockResolvedValue({ id: 1, username: 'admin', role: 'admin' })
  const wrapper = mount(LoginForm, { global: { stubs: uiStubs } })
  try {
    await wrapper.find('input[autocomplete="username"]').setValue('admin')
    await wrapper.find('input[autocomplete="current-password"]').setValue('password')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(false)
    await wrapper.find('input[autocomplete="one-time-code"]').setValue('123456')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('验证码无效')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(verify).toHaveBeenCalledWith('challenge-token', '123456')
    expect(wrapper.emitted('logined')).toHaveLength(1)
  } finally { wrapper.unmount() }
})

it('MFA 登录属于认证入口，旧账号失效不会拦截，也不会广播验证码错误为会话过期', async () => {
  api.bindAdminAccount(null)
  const expired = vi.fn()
  window.addEventListener(api.AUTH_EXPIRED_EVENT, expired)
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: { error: '验证码无效', code: 'mfa_invalid' } }), { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 8, username: 'admin', role: 'admin' })))
  vi.stubGlobal('fetch', fetcher)
  try {
    await expect(api.verifyMfa('challenge', '123456')).rejects.toThrow('验证码无效')
    expect(expired).not.toHaveBeenCalled()
    await api.verifyMfa('challenge', '123457')
    expect(localStorage.getItem(api.ACCOUNT_KEY)).toBe('8')
  } finally { window.removeEventListener(api.AUTH_EXPIRED_EVENT, expired) }
})
