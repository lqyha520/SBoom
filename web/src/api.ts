import type { Difficulty, MyTemplate, ScopeData } from './types'

const API = ''

/** 401 未登录/会话过期 —— 由调用方（App）捕获后展示登录页 */
export class AuthError extends Error {
  constructor(msg = '请先登录') {
    super(msg)
    this.name = 'AuthError'
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  // 同源部署（FastAPI 托管 / Vite 代理）默认携带 Cookie，无需显式 credentials
  const r = await fetch(API + url, init)
  if (!r.ok) {
    if (r.status === 401) throw new AuthError('请先登录')
    const e = await r.json().catch(() => ({} as any))
    const base = e?.detail?.error || e?.detail?.detail || `HTTP ${r.status}`
    // 500 = LLM 连接失败等后端错误，给出可操作的提示
    if (r.status === 500 || r.status === 502) {
      throw new Error(`${base}（LLM 服务连接失败，请检查「模型配置」中的接口地址和密钥）`)
    }
    throw new Error(base)
  }
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
export interface BatchItemReq { game_type: string; question_count: number }

export interface BatchRespSection {
  game_type: string
  topic?: string
  passage?: string
  questions: any[]
  missing_count?: number
}

export async function generateBatch(params: {
  grade: string
  subject: string
  keyword: string
  difficulty: Difficulty
  items: BatchItemReq[]
}): Promise<BatchRespSection[]> {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    difficulty: params.difficulty,
    items: params.items,
  }
  const d = await request<{ sections: BatchRespSection[] }>('/api/v1/generate-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
}) {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    game_type: params.game_type,
    difficulty: params.difficulty,
    question_count: params.question_count,
  }
  return request<{ questions: any[]; passage?: string; topic?: string }>('/api/v1/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/* ── 我的模板（服务端同步） ── */
export async function fetchTemplates(): Promise<MyTemplate[]> {
  const d = await request<{ templates: MyTemplate[] }>('/api/v1/me/templates')
  return d.templates || []
}

export async function upsertTemplate(tpl: MyTemplate): Promise<void> {
  await request('/api/v1/me/templates', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template: tpl }),
  })
}

export async function deleteTemplateOnServer(name: string): Promise<void> {
  await request(`/api/v1/me/templates?name=${encodeURIComponent(name)}`, { method: 'DELETE' })
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
