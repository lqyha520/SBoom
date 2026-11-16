import { afterEach, expect, it, vi } from 'vitest'
import { localFetch } from '../local-access'
import { bindAdminAccount, PERMISSIONS_CHANGED_EVENT } from '../api'

afterEach(() => vi.unstubAllGlobals())

it('先取得限定路径的凭证，再发送给本机服务且不传递登录凭据', async () => {
  bindAdminAccount(1)
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ token: 'proof' })))
    .mockResolvedValueOnce(new Response('{}'))
  vi.stubGlobal('fetch', fetch)
  await localFetch('http://127.0.0.1:17632/accounts/update', { method: 'POST', body: '{}' })
  expect(fetch.mock.calls[0]![0]).toBe('/api/v1/local-access/issue')
  expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({ path: '/accounts/update', method: 'POST' })
  const options = fetch.mock.calls[1]![1]
  expect(options.credentials).toBe('omit')
  expect(options.headers.get('X-Admin-Capability')).toBe('proof')
})

it('授权拒绝时不触发本机操作，并通知界面刷新权限', async () => {
  bindAdminAccount(1)
  const listener = vi.fn()
  window.addEventListener(PERMISSIONS_CHANGED_EVENT, listener)
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: '未授权', code: 'permission_denied' } }), { status: 403 }))
  vi.stubGlobal('fetch', fetch)
  await expect(localFetch('http://127.0.0.1:17632/accounts/add', { method: 'POST' })).rejects.toThrow('未授权')
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(listener).toHaveBeenCalledOnce()
  window.removeEventListener(PERMISSIONS_CHANGED_EVENT, listener)
})
