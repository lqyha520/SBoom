import type { Asset, DownloadTarget, CatalogSummary, PaperDetail, PaperList, SiteDocument, SiteHome, User } from '../types'
import { exerciseText } from '../presentation'

let base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
// #ifdef MP-WEIXIN
// 开发者工具联调：没有配置线上地址时，开发构建回落到本机后端。
// 需要在「详情 → 本地设置」勾选“不校验合法域名”，否则 wx.request 仍会被域名白名单拦下。
// 正式构建（import.meta.env.DEV 为 false）不走这里，只认 HTTPS 地址。
if (!base && import.meta.env.DEV) {
  base = (import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
}
// #endif
export const TOKEN_KEY = 'lc-consumer-session-v2'
let token = ''
let owner = ''
let generation = 0
let onUnauthorized: () => void = () => {}

export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = '') { super(message) }
}

export function configureSession(value: string, userId = '') {
  token = value
  owner = userId
  generation++
}
export function authGeneration() { return generation }
export function unauthorizedHandler(handler: () => void) { onUnauthorized = handler }
export function handleAuthFailure(status: number, code = '') {
  if (status === 401 || code === 'account_changed' || code === 'account_disabled') onUnauthorized()
}
export function authHeaders() {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = 'Bearer ' + token
  if (owner) headers['X-Mini-User'] = owner
  return headers
}
export function apiUrl(path: string) {
  if (!path.startsWith('/api/v1/')) throw new ApiError('无效的接口地址')
  // #ifdef MP-WEIXIN
  // 正式构建只接受 HTTPS 源；开发构建额外放行本机回环地址，便于连本机后端联调。
  const loopback = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/
  if (!/^https:\/\/[^/]+/.test(base) && !(import.meta.env.DEV && loopback.test(base))) {
    throw new ApiError('请先配置小程序的 HTTPS API 地址')
  }
  // #endif
  return base + path
}

export function request<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET', data?: unknown): Promise<T> {
  const epoch = generation
  const loginRequest = path.startsWith('/api/v1/mini/login') || path === '/api/v1/mini/register'
  return new Promise((resolve, reject) => {
    let url: string
    try { url = apiUrl(path) } catch (error) { reject(error); return }
    uni.request({
      url, method, data: data as Record<string, unknown> | undefined,
      header: { ...authHeaders(), 'Content-Type': 'application/json' }, timeout: 20000,
      success(response) {
        if (epoch !== generation) { reject(new ApiError('登录状态已变化', 409)); return }
        if (response.statusCode >= 200 && response.statusCode < 300) { resolve(response.data as T); return }
        const payload = response.data as { detail?: { error?: string; code?: string } | { msg?: string }[] | string }
        const detail = payload?.detail
        const code = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.code || '' : ''
        const message = typeof detail === 'string' ? detail : Array.isArray(detail)
          ? detail[0]?.msg?.replace(/^Value error, /, '') || '填写内容不符合要求，请检查后重试'
          : detail?.error || `请求失败 (${response.statusCode})`
        if (!loginRequest) handleAuthFailure(response.statusCode, code)
        reject(new ApiError(message, response.statusCode, code))
      },
      fail() { reject(new ApiError('网络连接失败，请稍后重试')) },
    })
  })
}

export function queryString(values: Record<string, string | number | boolean | null | undefined>) {
  return Object.entries(values).filter(([, value]) => value !== '' && value != null && value !== false)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`).join('&')
}
export function errorMessage(error: unknown) { return error instanceof Error ? exerciseText(error.message) : '操作失败，请稍后重试' }

export function fetchCatalog(params: Record<string, string | number | boolean | null | undefined> = {}) {
  return request<PaperList>('/api/v1/catalog/papers?' + queryString(params))
}

export function fetchCatalogSummary() { return request<CatalogSummary>('/api/v1/catalog/summary') }
export function fetchCatalogPaper(id: string) { return request<PaperDetail>('/api/v1/catalog/papers/' + encodeURIComponent(id)) }
export function favoriteCatalogPaper(id: string, favorite: boolean) {
  return request<{ favorite: boolean }>('/api/v1/catalog/papers/' + encodeURIComponent(id) + '/favorite', 'PUT', { favorite })
}
export function requestCatalogDownload(id: string, edition: 'original' | 'student' | 'answers' = 'original') {
  return request<DownloadTarget>('/api/v1/catalog/papers/' + encodeURIComponent(id) + '/download?edition=' + edition, 'POST')
}

/** 后台配置的运营内容：Banner、公告、分类、年级科目字典，一次请求拿全 */
export function fetchSiteHome() { return request<SiteHome>('/api/v1/site/home') }
export function fetchSiteDocument(key: 'agreement' | 'privacy') {
  return request<SiteDocument>('/api/v1/site/documents/' + encodeURIComponent(key))
}

/** 用户自助改资料：只传要改的字段（avatar 传空串表示恢复成默认形象）。 */
export function patchProfile(payload: { nickname?: string; avatar?: string }) {
  return request<User>('/api/v1/mini/me', 'PUT', payload)
}
export function patchPassword(currentPassword: string, newPassword: string) {
  return request<User>('/api/v1/mini/password', 'POST', { current_password: currentPassword, new_password: newPassword })
}
