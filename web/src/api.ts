import type { Difficulty, LlmConfig, ScopeData } from './types'

const API = ''

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + url, init)
  if (!r.ok) {
    const e = await r.json().catch(() => ({} as any))
    throw new Error(e?.detail?.error || e?.detail?.detail || `HTTP ${r.status}`)
  }
  return r.json()
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

/* ── 批量生成（整卷一次请求） ── */
export interface BatchItemReq { game_type: string; question_count: number }

export interface BatchRespSection {
  game_type: string
  topic?: string
  passage?: string
  questions: any[]
}

export async function generateBatch(params: {
  grade: string
  subject: string
  keyword: string
  difficulty: Difficulty
  items: BatchItemReq[]
  llm?: Partial<LlmConfig>
}): Promise<BatchRespSection[]> {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    difficulty: params.difficulty,
    items: params.items,
  }
  if (params.llm?.baseUrl) body.llm_base_url = params.llm.baseUrl
  if (params.llm?.model) body.llm_model = params.llm.model
  if (params.llm?.apiKey) body.llm_api_key = params.llm.apiKey
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
  llm?: Partial<LlmConfig>
}) {
  const body: Record<string, unknown> = {
    grade: params.grade,
    subject: params.subject,
    keyword: params.keyword,
    game_type: params.game_type,
    difficulty: params.difficulty,
    question_count: params.question_count,
    use_cache: false,
  }
  if (params.llm?.baseUrl) body.llm_base_url = params.llm.baseUrl
  if (params.llm?.model) body.llm_model = params.llm.model
  if (params.llm?.apiKey) body.llm_api_key = params.llm.apiKey
  return request<{ questions: any[]; passage?: string; topic?: string }>('/api/v1/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/* ── LLM 配置 ── */
export async function saveLlmConfig(cfg: LlmConfig): Promise<{ message: string }> {
  return request<{ message: string }>('/api/v1/config/llm', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
}

export async function testLlm(): Promise<{ reply: string }> {
  return request<{ reply: string }>('/api/v1/test-llm', { method: 'POST' })
}
