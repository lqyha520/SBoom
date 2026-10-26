/** 后台管理独立应用 —— API 封装（与工作台前端完全隔离） */

import type { ApiSchemas } from '../../shared/api-schema'
import { ApiError, AuthError, ForbiddenError, parseErrorDetail, retryableIdempotent, backoff } from '../../shared/http'
export { ApiError, AuthError, ForbiddenError } from '../../shared/http'

export type { UserInfo } from '../../shared/user'
import type { UserInfo } from '../../shared/user'

export interface AdminUser {
  id: number
  username: string
  role: string
  is_active: number
  created_at: string
  template_count: number
}

export interface AdminStats {
  users: number
  activeUsers: number
  admins: number
  templates: number
  llmConfigured: number
  feedbacks: number
  feedbacksOob: number
  generationUsage?: {
    requests: number; succeeded: number; failed: number; running: number; unknown: number; quota_used: number
    model_calls: number; reported_calls: number; prompt_tokens: number; completion_tokens: number
    daily_limit: number; failure_limit: number
  }
  securityWarnings?: string[]
  server: { model: string; encryption: string; version: string }
}

export interface AdminFeedback {
  id: number
  user_id: number | null
  username: string
  game_id: string
  is_oob: number
  comment: string | null
  created_at: string
}

/** 会话失效（401）——由 App 捕获后回到登录页 */


/** 401 广播事件：任何接口的会话失效都会通知外壳（App.vue 监听并回登录页），
 *  避免管理员停留在 Dashboard 里逐个操作报错直到手动刷新 */
export const FORBIDDEN_EVENT = 'lc-admin:forbidden'
export const AUTH_EXPIRED_EVENT = 'lc-admin:auth-expired'
export const ACCOUNT_CHANGED_EVENT = 'lc-admin:account-changed'
export const ACCOUNT_KEY = 'lc_uid'
let pageOwner = ''
let accountEpoch = 0
let accountInvalidated = false
export const adminAccountEpoch = () => accountEpoch
export function bindAdminAccount(id: string | number | null) { pageOwner = id == null ? '' : String(id); accountEpoch++; accountInvalidated = id == null }
export function accountChanged() {
  accountEpoch++
  accountInvalidated = true
  window.dispatchEvent(new CustomEvent(ACCOUNT_CHANGED_EVENT))
}

/** 默认超时：后台接口均为轻量操作，30s 足够（test-llm / 拉取模型列表除外） */
const DEFAULT_TIMEOUT_MS = 30_000
const TEST_LLM_TIMEOUT_MS = 610_000
const MODEL_LIST_TIMEOUT_MS = 65_000

export async function request<T>(url: string, init?: RequestInit, responseType: 'json' | 'blob' = 'json'): Promise<T> {
  const authEntry = url === '/api/v1/auth/login' || url === '/api/v1/auth/register' || url === '/api/v1/auth/me'
  if (accountInvalidated && !authEntry) throw new AuthError('登录账号已变化，请刷新后重试')
  const epoch = accountEpoch
  const headers = new Headers(init?.headers)
  if (pageOwner && !authEntry) {
    const actor = headers.get('X-Workspace-User')
    if (actor && actor !== pageOwner) throw new AuthError('登录账号已变化，请刷新后重试')
    headers.set('X-Workspace-User', pageOwner)
  }
  let r!: Response
  for (let attempt = 0; attempt < 2; attempt++) {
    if (!authEntry && epoch !== accountEpoch) throw new AuthError('登录账号已变化，请刷新后重试')
    const timeout = AbortSignal.timeout(url.endsWith('/reconciliations') && init?.method === 'POST' ? 180000 : url.includes('/admin/catalog/import') || url.includes('/editions/import') ? 120000 : url.includes('test-llm') ? TEST_LLM_TIMEOUT_MS : url.includes('/llm-models') ? MODEL_LIST_TIMEOUT_MS : DEFAULT_TIMEOUT_MS)
    try {
      r = await fetch(url, { ...init, headers, signal: init?.signal ? AbortSignal.any([timeout, init.signal]) : timeout })
    } catch (cause) {
      if (init?.signal?.aborted) throw cause
      if (attempt === 0 && retryableIdempotent(init?.method, 0)) { await backoff(); continue }
      throw new ApiError(cause instanceof Error && ['TimeoutError', 'AbortError'].includes(cause.name) ? '请求超时，请稍后重试' : '网络异常，请检查网络连接或后端服务状态')
    }
    if (attempt === 0 && retryableIdempotent(init?.method, r.status)) { await backoff(); continue }
    break
  }
  if (!authEntry && epoch !== accountEpoch) throw new AuthError('登录账号已变化，请刷新后重试')
  if (!r.ok) {
    const detail = parseErrorDetail(await r.json().catch(() => null), `请求失败（${r.status}）`)
    const credentialEntry = url === '/api/v1/auth/login' || url === '/api/v1/auth/register'
    if (detail.code === 'account_changed') { accountChanged(); throw new AuthError('登录账号已变化，请刷新后重试') }
    if (r.status === 401 && !credentialEntry) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail }))
      throw new AuthError(detail.code === 'reauth_required' ? '请重新验证登录后再次保存，当前修改已保留' : '登录已过期，请重新登录，当前修改已保留')
    }
    if (r.status === 403 && !credentialEntry) {
      window.dispatchEvent(new CustomEvent(FORBIDDEN_EVENT))
      throw new ForbiddenError(detail.message)
    }
    throw new ApiError(detail.message, r.status, detail.code, detail.requestId || r.headers.get('X-Correlation-ID') || '')
  }
  if (r.status === 204) return undefined as T
  const value = responseType === 'blob' ? await r.blob() as T : await r.json()
  if (!authEntry && epoch !== accountEpoch) throw new AuthError('登录账号已变化，请刷新后重试')
  return value
}

/* ── 认证 ── */
export async function login(username: string, password: string): Promise<UserInfo> {
  const user = await request<UserInfo>('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  bindAdminAccount(user.id)
  try { localStorage.setItem(ACCOUNT_KEY, String(user.id)) } catch { /* 请求头仍校验账号。 */ }
  return user
}

export async function logout(): Promise<void> {
  await request('/api/v1/auth/logout', { method: 'POST' })
  bindAdminAccount(null)
  try { localStorage.removeItem(ACCOUNT_KEY) } catch { /* 服务端会话已注销。 */ }
}

export async function fetchMe(): Promise<UserInfo | null> {
  try {
    return await request<UserInfo>('/api/v1/auth/me')
  } catch (e) {
    if (e instanceof AuthError) return null
    throw e
  }
}

/* ── 管理数据 ── */
export async function fetchAdminStats(): Promise<AdminStats> {
  return request('/api/v1/admin/stats')
}

export interface AdminUserPage { users: AdminUser[]; total: number; limit: number; offset: number }
export async function fetchAdminUsers(query = '', role: '' | 'user' | 'admin' = '', page = 1, pageSize = 20): Promise<AdminUserPage> {
  const params = new URLSearchParams()
  if (query) params.set('query', query)
  if (role) params.set('role', role)
  params.set('limit', String(pageSize))
  params.set('offset', String((page - 1) * pageSize))
  const suffix = params.toString()
  return request<AdminUserPage>(`/api/v1/admin/users${suffix ? `?${suffix}` : ''}`)
}

export async function adminCreateUser(u: ApiSchemas["AdminCreateUser"]): Promise<UserInfo> {
  return request('/api/v1/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(u),
  })
}

export async function adminUpdateUser(
  id: number,
  patch: ApiSchemas["AdminUpdateUser"],
): Promise<void> {
  await request(`/api/v1/admin/users/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function adminDeleteUser(id: number): Promise<void> {
  await request(`/api/v1/admin/users/${id}`, { method: 'DELETE' })
}

/* ── 用户反馈 ── */
export async function fetchAdminFeedbacks(limit = 100, oobOnly = false): Promise<AdminFeedback[]> {
  const d = await request<{ feedbacks: AdminFeedback[] }>(
    `/api/v1/admin/feedbacks?limit=${limit}${oobOnly ? '&oob_only=true' : ''}`,
  )
  return d.feedbacks || []
}

/* ── 查看用户模板 ── */
export interface UserTemplateMeta {
  id: number
  name: string
  updated_at: string
}

export async function fetchUserTemplates(userId: number): Promise<UserTemplateMeta[]> {
  const d = await request<{ templates: UserTemplateMeta[] }>(`/api/v1/admin/users/${userId}/templates`)
  return d.templates || []
}

export async function fetchUserTemplateContent(userId: number, tplId: number): Promise<Record<string, unknown>> {
  const d = await request<{ template: Record<string, unknown> }>(`/api/v1/admin/users/${userId}/templates/${tplId}`)
  return d.template
}

export async function fetchAdminLogs(lines = 200): Promise<string> {
  const d = await request<{ logs: string }>(`/api/v1/admin/logs?lines=${lines}`)
  return d.logs || ''
}

/* ── 全局模型配置（全体用户共用的 LLM 服务） ── */
export interface GlobalLlmConfig {
  revision?: string
  baseUrl: string
  model: string
  maxTokens?: number
  timeout: number
  hasKey: boolean
  models?: TextModelProfile[]
}

export type TextModelProfile = Omit<ApiSchemas["TextModelProfile"], 'apiKey'> & { hasKey: boolean }

export async function fetchLlmConfig(): Promise<GlobalLlmConfig> {
  return request('/api/v1/admin/llm-config')
}

export async function saveLlmConfig(cfg: ApiSchemas["TextModelProfiles"] | ApiSchemas["AdminLlmConfigIn"]): Promise<GlobalLlmConfig & { message: string }> {
  return request('/api/v1/admin/llm-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
}

/** 清除全局模型配置（含已存密钥）：密钥疑似泄露/换服务商时使用 */
export async function clearLlmConfig(revision?: string): Promise<GlobalLlmConfig & { message: string }> {
  return request('/api/v1/admin/llm-config', { method: 'DELETE', headers: revision ? { 'If-Match': revision } : {} })
}

export async function testLlm(cfg?: ApiSchemas["AdminLlmConfigIn"]): Promise<{ reply: string }> {
  return request('/api/v1/admin/test-llm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg || {}),
  })
}

/** 拉取模型服务 GET /models 返回的模型 ID，用于下拉选择；失败时仍可手动填写。 */
export async function fetchLlmModels(cfg: ApiSchemas["AdminLlmModelsIn"]): Promise<{ models: string[]; count: number }> {
  return request('/api/v1/admin/llm-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
}
