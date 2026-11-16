import { request } from './api'

/** 浏览器只拿到指定操作的 30 秒凭证，不把登录 Cookie 交给本机桥。 */
export async function localFetch(url: string, init: RequestInit = {}) {
  const parsed = new URL(url)
  if (parsed.origin !== 'http://127.0.0.1:17632') throw new Error('不支持的本机服务地址')
  const headers = new Headers(init.headers)
  if (parsed.pathname !== '/health') {
    const result = await request<{ token: string }>('/api/v1/local-access/issue', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: parsed.pathname + parsed.search, method: init.method || 'GET' }),
    })
    headers.set('X-Admin-Capability', result.token)
  }
  return fetch(url, { ...init, headers, credentials: 'omit' })
}
