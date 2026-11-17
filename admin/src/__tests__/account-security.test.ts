import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import AccountSecurity from '../components/AccountSecurity.vue'
import * as security from '../account-security'
import QRCode from 'qrcode'
import { uiStubs } from '../../../shared/test/ui-stubs'

vi.mock('../account-security')
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn() } }))
const secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
const enrollment = { secret, otpauth_url: `otpauth://totp/LearnCoach%3Ademo?secret=${secret}&issuer=LearnCoach&algorithm=SHA1&digits=6&period=30` }
let wrapper: VueWrapper
const button = (name: string) => wrapper.findAll('button').find(item => item.text() === name)!
async function render() {
  wrapper = mount(AccountSecurity, { global: { stubs: { ...uiStubs, UCard: { template: '<div><slot /></div>' } } } })
  await flushPromises()
}
async function begin() {
  await button('手机已准备好，生成二维码').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-14T09:00:00Z'))
  vi.mocked(security.mfaStatus).mockResolvedValue({ enabled: false })
  vi.mocked(security.listSessions).mockResolvedValue({ sessions: [] })
  vi.mocked(security.setupMfa).mockResolvedValue(enrollment)
  vi.mocked(QRCode.toDataURL).mockImplementation(async () => 'data:image/png;base64,fixture')
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.restoreAllMocks(); vi.resetAllMocks() })

it('用户准备好才生成绑定信息，扫码优先，确认成功后清除二维码和密钥', async () => {
  await render()
  expect(wrapper.text()).toContain('1. 在手机上安装验证器')
  expect(security.setupMfa).not.toHaveBeenCalled()
  await begin()
  expect(QRCode.toDataURL).toHaveBeenCalledWith(enrollment.otpauth_url, expect.objectContaining({ margin: 4, width: 240 }))
  expect(wrapper.find('img').attributes('src')).toMatch(/^data:image\/png/)
  expect(wrapper.find('details').attributes('open')).toBeUndefined()
  expect(security.changeMfa).not.toHaveBeenCalled()
  vi.mocked(security.changeMfa).mockResolvedValue({ enabled: true })
  vi.mocked(security.mfaStatus).mockResolvedValue({ enabled: true })
  await wrapper.find('input[autocomplete="one-time-code"]').setValue('123456')
  await wrapper.find('form').trigger('submit'); await flushPromises()
  expect(security.changeMfa).toHaveBeenCalledWith('confirm', '123456')
  expect(wrapper.text()).toContain('登录二次验证已开启')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('input[readonly]').exists()).toBe(false)
})

it('十分钟过期会清除凭据和验证码，并允许重新生成后重试', async () => {
  await render(); await begin()
  await wrapper.find('input[autocomplete="one-time-code"]').setValue('123456')
  await vi.advanceTimersByTimeAsync(600_000)
  expect(wrapper.text()).toContain('本次二维码已过期')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('input[readonly]').exists()).toBe(false)
  expect(wrapper.find('form').exists()).toBe(false)
  expect(security.changeMfa).not.toHaveBeenCalled()
  await button('重新生成二维码').trigger('click'); await flushPromises()
  expect(security.setupMfa).toHaveBeenCalledTimes(2)
  expect(wrapper.find('img').exists()).toBe(true)
  expect((wrapper.find('input[autocomplete="one-time-code"]').element as HTMLInputElement).value).toBe('')
})

it('二维码渲染失败仍能手动添加，复制被拒绝时显示可执行的提示', async () => {
  vi.mocked(QRCode.toDataURL).mockRejectedValue(new Error('render failed'))
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValueOnce(new Error('denied')).mockResolvedValue(undefined)
  await render(); await begin()
  expect(wrapper.text()).toContain('二维码暂时无法显示')
  expect(wrapper.find('details').attributes('open')).toBeDefined()
  await button('复制密钥').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('请选中下面的密钥手动复制')
  await button('复制密钥').trigger('click'); await flushPromises()
  expect(copy).toHaveBeenLastCalledWith(secret)
  expect(wrapper.text()).toContain('已复制，请粘贴到验证器')
  expect(security.changeMfa).not.toHaveBeenCalled()
})

it('暂不设置会清除绑定信息，离开页面后的请求不再渲染二维码', async () => {
  await render(); await begin()
  await button('暂不设置').trigger('click')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('input[readonly]').exists()).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
  let finish!: (value: typeof enrollment) => void
  vi.mocked(security.setupMfa).mockReturnValue(new Promise(resolve => { finish = resolve }))
  await button('手机已准备好，生成二维码').trigger('click')
  wrapper.unmount()
  finish(enrollment); await flushPromises()
  expect(QRCode.toDataURL).toHaveBeenCalledTimes(1)
  expect(security.changeMfa).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('绑定信息缺失或协议不符时不展示空密钥或外部添加链接', async () => {
  vi.mocked(security.setupMfa).mockResolvedValue({ secret, otpauth_url: 'https://example.com' })
  await render(); await begin()
  expect(wrapper.text()).toContain('未能生成有效的绑定信息')
  expect(wrapper.find('input[readonly]').exists()).toBe(false)
  expect(QRCode.toDataURL).not.toHaveBeenCalled()
})
