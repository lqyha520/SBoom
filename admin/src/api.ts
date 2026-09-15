/** 后台管理独立应用 —— API 封装（与工作台前端完全隔离） */

export interface UserInfo { id: number; username: string; role: string }

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
    requests: number; succeeded: number; running: number; unknown: number
    model_calls: number; reported_calls: number; prompt_tokens: number; completion_tokens: number; daily_limit: number
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
export class AuthError extends Error {}

/** 401 广播事件：任何接口的会话失效都会通知外壳（App.vue 监听并回登录页），
 *  避免管理员停留在 Dashboard 里逐个操作报错直到手动刷新 */
export const AUTH_EXPIRED_EVENT = 'lc-admin:auth-expired'

/** 默认超时：后台接口均为轻量操作，30s 足够（test-llm 除外，可能要等首 token） */
const DEFAULT_TIMEOUT_MS = 30_000
const TEST_LLM_TIMEOUT_MS = 120_000

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(url.includes('test-llm') ? TEST_LLM_TIMEOUT_MS : DEFAULT_TIMEOUT_MS),
    })
  } catch (e: any) {
    if (e?.name === 'TimeoutError' || e?.name === 'AbortError') throw new Error('请求超时，请稍后重试')
    throw new Error('网络异常，请检查网络连接或后端服务状态')
  }
  if (!r.ok) {
    if (r.status === 401) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
      throw new AuthError('登录已过期')
    }
    if (r.status === 403) throw new AuthError('没有管理员权限')
    const e = await r.json().catch(() => ({} as any))
    // FastAPI 的 detail 可能是 {error, detail} 对象，也可能是纯字符串
    const d = e?.detail
    const base = typeof d === 'string' ? d : (d?.error || d?.detail || `HTTP ${r.status}`)
    throw new Error(base)
  }
  if (r.status === 204) return undefined as T
  return r.json()
}

/* ── 认证 ── */
export async function login(username: string, password: string): Promise<UserInfo> {
  return request<UserInfo>('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function logout(): Promise<void> {
  await request('/api/v1/auth/logout', { method: 'POST' }).catch(() => {})
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

export async function fetchAdminUsers(query = '', role: '' | 'user' | 'admin' = ''): Promise<AdminUser[]> {
  const params = new URLSearchParams()
  if (query) params.set('query', query)
  if (role) params.set('role', role)
  const suffix = params.toString()
  const d = await request<{ users: AdminUser[] }>(`/api/v1/admin/users${suffix ? `?${suffix}` : ''}`)
  return d.users || []
}

export async function adminCreateUser(u: { username: string; password: string; role: string }): Promise<UserInfo> {
  return request('/api/v1/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(u),
  })
}

export async function adminUpdateUser(
  id: number,
  patch: { password?: string; role?: string; is_active?: boolean },
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
  baseUrl: string
  model: string
  timeout: number
  hasKey: boolean
}

export async function fetchLlmConfig(): Promise<GlobalLlmConfig> {
  return request('/api/v1/admin/llm-config')
}

export async function saveLlmConfig(cfg: {
  baseUrl: string
  model: string
  apiKey: string
  timeout: number
}): Promise<{ message: string; hasKey: boolean }> {
  return request('/api/v1/admin/llm-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
}

/** 清除全局模型配置（含已存密钥）：密钥疑似泄露/换服务商时使用 */
export async function clearLlmConfig(): Promise<{ message: string }> {
  return request('/api/v1/admin/llm-config', { method: 'DELETE' })
}

export async function testLlm(cfg?: {
  baseUrl: string
  model: string
  apiKey: string
  timeout: number
}): Promise<{ reply: string }> {
  return request('/api/v1/admin/test-llm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg || {}),
  })
}
