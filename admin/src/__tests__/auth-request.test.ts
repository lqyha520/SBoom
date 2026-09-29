import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ACCOUNT_CHANGED_EVENT, ACCOUNT_KEY, accountChanged, bindAdminAccount, login, logout, request, saveLlmConfig } from '../api'

beforeEach(() => { localStorage.clear(); bindAdminAccount(1) })
afterEach(() => { vi.unstubAllGlobals(); bindAdminAccount(null) })

it('wrong login credentials show the server message without expiring the active session', async () => {
  const dispatch = vi.spyOn(window, 'dispatchEvent')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: '用户名或密码错误' } }), { status: 401 })))
  try {
    await expect(login('wrong', 'password')).rejects.toThrow('用户名或密码错误')
    expect(dispatch).not.toHaveBeenCalled()
  } finally { dispatch.mockRestore() }
})

it('退出失败会向界面返回错误，保留账号信息供重试', async () => {
  localStorage.setItem(ACCOUNT_KEY, '1')
  const fetchMock = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await expect(logout()).rejects.toThrow('网络异常')
  expect(localStorage.getItem(ACCOUNT_KEY)).toBe('1')
  await logout()
  expect(new Headers(fetchMock.mock.calls[1][1].headers).get('X-Workspace-User')).toBe('1')
  expect(localStorage.getItem(ACCOUNT_KEY)).toBeNull()
})

it('通用写接口绑定当前页面账号，保留其他请求头', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await saveLlmConfig({ baseUrl: 'https://example.invalid', model: 'fixture', apiKey: '', timeout: 30 })
  const headers = new Headers(fetchMock.mock.calls[0][1].headers)
  expect(headers.get('X-Workspace-User')).toBe('1')
  expect(headers.get('Content-Type')).toBe('application/json')
})

it('账号冲突通知外壳停止旧页面操作', async () => {
  const changed = vi.fn()
  window.addEventListener(ACCOUNT_CHANGED_EVENT, changed)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'account_changed' } }), { status: 409 })))
  try { await expect(request('/api/v1/admin/users')).rejects.toThrow('账号已变化'); expect(changed).toHaveBeenCalledOnce() }
  finally { window.removeEventListener(ACCOUNT_CHANGED_EVENT, changed) }
})

it('账号切换后忽略迟到的旧请求结果', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const pending = request('/api/v1/admin/users')
  accountChanged()
  finish(new Response('{}'))
  await expect(pending).rejects.toThrow('账号已变化')
  await expect(request('/api/v1/admin/users', { method: 'POST' })).rejects.toThrow('账号已变化')
  expect(fetch).toHaveBeenCalledOnce()
})

it('旧页面显式携带的账号不能被新的公共账号覆盖', async () => {
  vi.stubGlobal('fetch', vi.fn())
  await expect(request('/api/v1/admin/users', { method: 'POST', headers: { 'X-Workspace-User': '2' } })).rejects.toThrow('账号已变化')
  expect(fetch).not.toHaveBeenCalled()
})

it('登录不携带旧账号校验，成功后绑定新的账号', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id: 2, username: 'new', role: 'admin' }))).mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await login('new', 'fixture')
  expect(new Headers(fetchMock.mock.calls[0][1].headers).has('X-Workspace-User')).toBe(false)
  await request('/api/v1/admin/users')
  expect(new Headers(fetchMock.mock.calls[1][1].headers).get('X-Workspace-User')).toBe('2')
  expect(localStorage.getItem(ACCOUNT_KEY)).toBe('2')
})


it('422 保留字段校验详情，409 保留业务码和关联 ID', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ loc: ['body', 'phone'], msg: '不符合电话格式' }] }), { status: 422 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { error: '版本已变化', code: 'revision_conflict' } }), { status: 409, headers: { 'X-Correlation-ID': 'trace-1' } })))
  await expect(request('/api/v1/admin/example', { method: 'PUT' })).rejects.toMatchObject({ status: 422, message: 'phone：不符合电话格式' })
  await expect(request('/api/v1/admin/example', { method: 'PUT' })).rejects.toMatchObject({ status: 409, code: 'revision_conflict', requestId: 'trace-1' })
})

it('网关错误仅重试 GET，写入请求保留供用户显式重试', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 502 })).mockResolvedValueOnce(new Response('{"ok":true}')).mockResolvedValueOnce(new Response('{}', { status: 502 }))
  vi.stubGlobal('fetch', fetcher)
  await expect(request('/api/v1/admin/example')).resolves.toEqual({ ok: true })
  await expect(request('/api/v1/admin/example', { method: 'POST' })).rejects.toMatchObject({ status: 502 })
  expect(fetcher).toHaveBeenCalledTimes(3)
})
