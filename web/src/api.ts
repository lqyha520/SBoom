import type { Difficulty, MyTemplate, Question, ScopeData } from './types'

const API = ''
export const AUTH_CHANGED_EVENT = 'lc:auth-changed'
let workspaceOwner = ''
export function bindWorkspaceOwner(owner: string) { workspaceOwner = owner }
export function captureWorkspaceGuard() {
  const owner = workspaceOwner
  return () => {
    if (owner !== workspaceOwner) throw new ApiError('登录账号已变化，请刷新后重试', 409, 'account_changed')
  }
}

export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = '', public requestId = '') {
    super(message)
    this.name = 'ApiError'
  }
}

/** 401 未登录/会话过期 —— 由调用方（App）捕获后展示登录页 */
export class AuthError extends Error {
  constructor(msg = '请先登录') {
    super(msg)
    this.name = 'AuthError'
  }
}

/** 各接口默认超时：生成类请求要等 LLM（可能 2 分钟+），其余接口 30s 足够。
 *  无超时的 fetch 会让启动 splash 在后端挂起时无限转圈 */
const DEFAULT_TIMEOUT_MS = 30_000
const GENERATE_TIMEOUT_MS = 300_000

export async function request<T>(url: string, init?: RequestInit, timeoutOverrideMs?: number): Promise<T> {
  const paid = url.startsWith('/api/v1/generate') || url === '/api/v1/validate'
  const timeoutMs = timeoutOverrideMs ?? (paid ? GENERATE_TIMEOUT_MS : DEFAULT_TIMEOUT_MS)
  const headers = new Headers(init?.headers)
  if (workspaceOwner && !url.startsWith('/api/v1/auth/')) headers.set('X-Workspace-User', workspaceOwner)
  const requestId = headers.get('X-Request-ID') || ''
  let r: Response
  try {
    r = await fetch(API + url, {
      ...init,
      headers,
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (e: any) {
    if (e?.name === 'TimeoutError' || e?.name === 'AbortError') {
      throw new ApiError(paid ? '请求超时，未自动重发；可查询原请求结果' : '请求超时，请稍后重试', 0, 'network_unknown', requestId)
    }
    throw new ApiError(paid ? '网络中断，未自动重发；可查询原请求结果' : '网络异常，请检查连接', 0, 'network_unknown', requestId)
  }
  if (!r.ok) {
    if (r.status === 401) {
      // 登录/注册接口的 401 是「用户名或密码错误」，要展示后端原文并提示可注册；
      // 其余接口的 401 才是会话过期，转为「请先登录」让 App 弹登录页
      if (url === '/api/v1/auth/login' || url === '/api/v1/auth/register') {
        const e = await r.json().catch(() => ({} as any))
        const d = e?.detail
        const base = typeof d === 'string' ? d : (d?.error || d?.detail || '登录失败，请重试')
        throw new ApiError(base, 401, d?.code || '')
      }
      if (workspaceOwner) window.dispatchEvent(new Event(AUTH_CHANGED_EVENT))
      throw new AuthError('请先登录')
    }
    const e = await r.json().catch(() => ({} as any))
    // FastAPI 的 detail 可能是 {error, detail} 对象，也可能是纯字符串/校验数组
    const d = e?.detail
    const base = typeof d === 'string' ? d : (d?.error || d?.detail || `HTTP ${r.status}`)
    if (d?.code === 'account_changed') window.dispatchEvent(new Event(AUTH_CHANGED_EVENT))
    throw new ApiError(base, r.status, d?.code || '', d?.request_id || requestId)
  }
  if (r.status === 204) return undefined as T
  return r.json()
}

/* ── 认证 ── */
export interface UserInfo { id: number; username: string; role: string }

export async function register(username: string, password: string): Promise<UserInfo> {
  return request<UserInfo>('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function login(username: string, password: string): Promise<UserInfo> {
  return request<UserInfo>('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function logout(): Promise<void> {
  await request<{ status: string }>('/api/v1/auth/logout', { method: 'POST' })
}

export async function fetchMe(): Promise<UserInfo | null> {
  try {
    return await request<UserInfo>('/api/v1/auth/me')
  } catch (e) {
    if (e instanceof AuthError) return null
    throw e
  }
}

/* ── 年级/科目可用列表 ── */
export async function fetchAvailable(): Promise<Record<string, string[]>> {
  const d = await request<{ available: Record<string, string[]> }>('/api/v1/scope/available')
  return d.available
}

/* ── 知识点范围 ── */
export async function fetchScope(grade: string, subject: string): Promise<ScopeData> {
  return request<ScopeData>(`/api/v1/scope?grade=${encodeURIComponent(grade)}&subject=${encodeURIComponent(subject)}`)
}

/* ── 批量生成（整卷一次请求）。模型配置由管理员在后台统一管理，请求不携带密钥 ── */
export interface BatchItemReq { game_type: string; question_count: number; section_id: string }

export interface BatchRespSection {
  game_type: string
  section_id?: string | null
  topic?: string
  passage?: string
  questions: Question[]
  missing_count?: number
  quality_warnings?: string[]
}

export interface BatchParams {
  grade: string
  subject: string
  keyword: string
  difficulty: Difficulty
  items: BatchItemReq[]
}

export async function generateBatch(params: BatchParams, requestId: string = crypto.randomUUID()): Promise<BatchRespSection[]> {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    difficulty: params.difficulty,
    items: params.items,
  }
  const d = await request<{ sections: BatchRespSection[] }>('/api/v1/generate-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
    body: JSON.stringify(body),
  })
  return d.sections || []
}

/* ── 单题型生成（重试用） ── */
export async function generateOne(params: {
  grade: string
  subject: string
  keyword: string
  game_type: string
  difficulty: Difficulty
  question_count: number
}, requestId: string = crypto.randomUUID()) {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    game_type: params.game_type,
    difficulty: params.difficulty,
    question_count: params.question_count,
  }
  return request<BatchRespSection>('/api/v1/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
    body: JSON.stringify(body),
  })
}

export interface GenerationStatus {
  request_id: string
  status: 'running' | 'succeeded' | 'failed' | 'unknown'
  result: { sections: BatchRespSection[] } | null
  error?: { error?: string } | null
  error_status: number
  cache_expired: boolean
}

export function fetchGenerationStatus(requestId: string) {
  return request<GenerationStatus>('/api/v1/me/generations/' + encodeURIComponent(requestId))
}

export interface GenerationUsage {
  requests: number
  succeeded: number
  running: number
  unknown: number
  model_calls: number
  reported_calls: number
  prompt_tokens: number
  completion_tokens: number
  daily_limit: number
}

export function fetchGenerationUsage() {
  return request<GenerationUsage>('/api/v1/me/usage')
}

/* ── 我的模板（服务端同步） ── */
export async function fetchTemplates(): Promise<MyTemplate[]> {
  const d = await request<{ templates: MyTemplate[] }>('/api/v1/me/templates')
  return d.templates || []
}

export async function upsertTemplate(tpl: MyTemplate): Promise<number> {
  const { _revision, _syncState, _syncError, ...template } = tpl
  const result = await request<{ revision: number }>('/api/v1/me/templates', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template, expected_revision: _revision || 0 }),
  })
  return result.revision
}

export async function deleteTemplateOnServer(name: string, revision: number): Promise<void> {
  await request(`/api/v1/me/templates?name=${encodeURIComponent(name)}&expected_revision=${revision}`, { method: 'DELETE' })
}

export async function bulkUploadTemplates(templates: MyTemplate[]): Promise<number> {
  const d = await request<{ imported: number }>('/api/v1/me/templates/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ templates }),
  })
  return d.imported || 0
}
/* 后台管理功能在独立系统 /admin（admin/ 前端应用），此处不包含管理端 API */
