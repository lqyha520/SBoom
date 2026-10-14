import { ApiError as SharedApiError, parseErrorDetail, retryableIdempotent, backoff } from '../../../shared/http'
import type { RequestScope } from './latest-request'
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

export class ApiError extends SharedApiError {}

export function configureSession(value: string, userId = '') {
  if (value === token && (!owner || !userId || owner === userId)) { if (userId) owner = userId; return false }
  token = value
  owner = userId
  generation++
  invalidatePersonal()
  for (const cancel of activeReads) cancel()
  activeReads.clear()
  return true
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
// #ifdef MP-WEIXIN
/** 只有开发者工具能连本机后端：真机上 127.0.0.1 指向手机自己，请求必然失败。 */
function loopbackUsableHere() {
  try { return (uni.getSystemInfoSync() as { platform?: string }).platform === 'devtools' } catch { return false }
}
// #endif
export function apiUrl(path: string) {
  if (!path.startsWith('/api/v1/')) throw new ApiError('无效的接口地址')
  // #ifdef MP-WEIXIN
  // 正式构建只接受 HTTPS 源；开发构建额外放行本机回环地址，便于连本机后端联调。
  const loopback = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/
  if (!/^https:\/\/[^/]+/.test(base) && !(import.meta.env.DEV && loopback.test(base))) {
    throw new ApiError('请先配置小程序的 HTTPS API 地址')
  }
  // 把「拿开发构建去上传」这种误操作变成一句能自解释的提示，而不是含义不明的"网络错误"。
  if (loopback.test(base) && !loopbackUsableHere()) {
    throw new ApiError('当前安装包内置的是本机调试地址，请改用正式构建（发行）重新上传')
  }
  // #endif
  return base + path
}

function networkOnce<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET', data?: unknown, scope?: RequestScope, anonymous = false): Promise<T> {
  const epoch = generation
  const startedAt = Date.now()
  const loginRequest = path.startsWith('/api/v1/mini/login') || path === '/api/v1/mini/register'
  return new Promise((resolve, reject) => {
    let url: string
    try { url = apiUrl(path) } catch (error) { reject(error); return }
    let task: UniApp.RequestTask | undefined
    let settled = false
    let unregister = () => {}
    const cancel = () => { if (!settled) { settled = true; reject(new ApiError('请求已取消', 0, 'cancelled')); task?.abort(); cleanup() } }
    const cleanup = () => { unregister(); activeReads.delete(cancel) }
    if (method === 'GET' || path === '/api/v1/catalog/window') {
      if (!anonymous) activeReads.add(cancel)
      unregister = scope?.onCancel(cancel) || unregister
    }
    if (settled) return
    task = uni.request({
      url, method, data: data as Record<string, unknown> | undefined,
      header: { ...(anonymous ? {} : authHeaders()), 'Content-Type': 'application/json' }, timeout: 20000,
      success(response) {
        if (settled) return
        settled = true; cleanup()
        if (!anonymous && epoch !== generation) { reject(new ApiError('登录状态已变化', 409)); return }
        if (response.statusCode >= 200 && response.statusCode < 300) {
          uni.$emit?.('lc-performance', { kind: path.startsWith('/api/v1/catalog/papers?') ? 'catalog_api' : 'api', value: Date.now() - startedAt })
          if (method !== 'GET' && path !== '/api/v1/catalog/window') invalidatePersonal()
          resolve(response.data as T); return
        }
        const { message, code, requestId } = parseErrorDetail(response.data, `请求失败 (${response.statusCode})`)
        if (!anonymous && !loginRequest) handleAuthFailure(response.statusCode, code)
        if (response.statusCode >= 500) uni.$emit?.('lc-diagnostic', 'server')
        reject(new ApiError(message, response.statusCode, code, requestId || String(response.header?.['X-Correlation-ID'] || response.header?.['x-correlation-id'] || '')))
      },
      fail() { if (!settled) { settled = true; cleanup(); uni.$emit?.('lc-diagnostic', 'network'); reject(new ApiError('网络连接失败，请稍后重试')) } },
    })
  })
}

async function network<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET', data?: unknown, scope?: RequestScope, anonymous = false): Promise<T> {
  const epoch = generation
  let cancelled = false
  const unregister = scope?.onCancel(() => { cancelled = true })
  try {
    try { return await networkOnce<T>(path, method, data, scope, anonymous) }
    catch (error) {
      if (!(error instanceof ApiError) || error.code === 'cancelled' || cancelled || (!anonymous && epoch !== generation) || !retryableIdempotent(method, error.status)) throw error
      await backoff()
      if (cancelled || (!anonymous && epoch !== generation)) throw new ApiError('请求已取消', 0, 'cancelled')
      return await networkOnce<T>(path, method, data, scope, anonymous)
    }
  } finally { unregister?.() }
}

const activeReads = new Set<() => void>()
export interface ReadOptions { scope?: RequestScope; force?: boolean; anonymous?: boolean }
const metadata = new Map<string, { expires: number; value: unknown }>()
const pending = new Map<string, { promise: Promise<unknown>; users: number; cancel: () => void }>()
const publicPaths = new Set(['/api/v1/site/home', '/api/v1/site/topics', '/api/v1/site/catalog-tags'])
const personalPaths = new Set(['/api/v1/mini/me', '/api/v1/catalog/summary', '/api/v1/mini/messages?unread=false&offset=0&limit=1'])
function invalidatePersonal() {
  for (const cached of [...metadata.keys(), ...pending.keys()]) if (personalPaths.has(cached.slice(cached.indexOf(':') + 1))) { metadata.delete(cached); pending.delete(cached) }
}
let metadataEpoch = 0
export function invalidateMetadata() { metadataEpoch++; metadata.clear(); pending.clear() }
export function request<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET', data?: unknown, options: ReadOptions = {}): Promise<T> {
  // 冷启动公开内容独立于登录恢复；不携带 token、不复用个人缓存、不触发退出。
  if (options.anonymous) {
    const pathname = path.split('?')[0]
    if (method !== 'GET' || (!publicPaths.has(pathname) && pathname !== '/api/v1/catalog/papers' && pathname !== '/api/v1/catalog/summary')) {
      return Promise.reject(new ApiError('该接口不支持公开读取'))
    }
    if (!publicPaths.has(path)) return network<T>(path, method, data, options.scope, true)
  }
  // 个人摘要只在同一登录代际内短暂缓存，写入前后立即失效。
  if (method !== 'GET' || (!publicPaths.has(path) && !personalPaths.has(path))) {
    if (method !== 'GET' && path !== '/api/v1/catalog/window') {
      // 只让个人读取失效，公共运营配置继续命中缓存。
      invalidatePersonal()
    }
    // 个人写操作不会修改公共配置；公共摘要由过期、手动刷新和账号切换失效。
    return network<T>(path, method, data, options.scope)
  }
  // 白名单内运营配置与账号无关，始终公开读取并跨登录恢复复用。
  const publicRead = publicPaths.has(path)
  const key = (publicRead ? 'public' : generation) + ':' + path
  if (options.force) { metadata.delete(key); pending.delete(key) }
  const cached = metadata.get(key)
  if (!options.force && cached && cached.expires > Date.now()) return Promise.resolve(JSON.parse(JSON.stringify(cached.value)) as T)
  let entry = pending.get(key)
  if (!entry) {
    let cancel = () => {}
    const epoch = generation, cacheEpoch = metadataEpoch
    const promise = network<T>(path, method, data, { onCancel(fn) { cancel = fn; return () => {} } }, publicRead).then(value => {
      if ((publicRead || epoch === generation) && cacheEpoch === metadataEpoch && pending.get(key)?.promise === promise) metadata.set(key, { value, expires: Date.now() + (personalPaths.has(path) ? 20_000 : 60_000) })
      return value
    })
    entry = { promise, users: 0, cancel: () => cancel() }
    pending.set(key, entry)
    const same = entry
    void promise.finally(() => { if (pending.get(key) === same) pending.delete(key) }).catch(() => {})
  }
  const shared = entry
  shared.users++
  return new Promise<T>((resolve, reject) => {
    let done = false, unregister = () => {}
    const release = () => { if (done) return false; done = true; unregister(); shared.users--; return true }
    unregister = options.scope?.onCancel(() => {
      if (release()) {
        // 页面在同一轮更新中切换读取者时保留在途请求；真正离开仍会取消。
        if (!shared.users) void Promise.resolve().then(() => {
          if (!shared.users) { shared.cancel(); if (pending.get(key) === shared) pending.delete(key) }
        })
        reject(new ApiError('请求已取消', 0, 'cancelled'))
      }
    }) || unregister
    shared.promise.then(value => { if (release()) resolve(JSON.parse(JSON.stringify(value)) as T) }, error => { if (release()) reject(error) })
  })
}

export function queryString(values: Record<string, string | number | boolean | null | undefined>) {
  return Object.entries(values).filter(([, value]) => value !== '' && value != null)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`).join('&')
}
export function errorMessage(error: unknown) { return error instanceof Error ? exerciseText(error.message) : '操作失败，请稍后重试' }

export function fetchCatalog(params: Record<string, string | number | boolean | null | undefined> = {}, options: ReadOptions = {}) {
  return request<PaperList>('/api/v1/catalog/papers?' + queryString(params), 'GET', undefined, options)
}

export function fetchCatalogSummary(options: ReadOptions = {}) { return request<CatalogSummary>('/api/v1/catalog/summary', 'GET', undefined, options) }
export function fetchCatalogPaper(id: string, options: ReadOptions = {}) { return request<PaperDetail>('/api/v1/catalog/papers/' + encodeURIComponent(id), 'GET', undefined, options) }
export function favoriteCatalogPaper(id: string, favorite: boolean) {
  return request<{ favorite: boolean }>('/api/v1/catalog/papers/' + encodeURIComponent(id) + '/favorite', 'PUT', { favorite })
}
export function requestCatalogDownload(id: string, edition: 'original' | 'student' | 'answers' = 'original') {
  return request<DownloadTarget>('/api/v1/catalog/papers/' + encodeURIComponent(id) + '/download?edition=' + edition, 'POST')
}

/** 后台配置的运营内容：Banner、公告、分类、年级科目字典，一次请求拿全 */
export function fetchSiteHome(options: ReadOptions = {}) { return request<SiteHome>('/api/v1/site/home', 'GET', undefined, options) }
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

export const fetchCatalogWindow = (ids: string[], options: ReadOptions = {}) => request<{ items: PaperDetail[] }>('/api/v1/catalog/window', 'POST', { ids }, options)
