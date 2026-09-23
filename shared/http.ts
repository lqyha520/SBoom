/**
 * 工作台与管理后台共用的 HTTP 错误模型与请求选项。
 *
 * 两个应用各自维护 `request()`（请求头、超时策略、401 广播事件都不同），
 * 但错误类型必须一致：调用方靠 `status / code / requestId` 决定是否可重试、
 * 是否为会话失效、是否为权限不足，而不是靠猜测错误文案。
 */

/** 后端返回的业务错误（含 HTTP 状态码、后端 code、请求 ID） */
export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = '', public requestId = '') {
    super(message)
    this.name = 'ApiError'
  }
}

/** 401：未登录 / 会话过期 —— 由应用外壳捕获后展示登录页 */
export class AuthError extends Error {
  readonly status = 401
  constructor(message = '请先登录') {
    super(message)
    this.name = 'AuthError'
  }
}

/** 403：已登录但没有权限（例如普通用户访问管理接口）—— 与「未登录」区分展示 */
export class ForbiddenError extends Error {
  readonly status = 403
  constructor(message = '没有管理员权限') {
    super(message)
    this.name = 'ForbiddenError'
  }
}

export interface RequestOptions {
  /** 单次请求超时（毫秒）；由调用方按接口特性显式指定，而不是在 request() 里按 URL 猜 */
  timeoutMs?: number
  /** 响应体解析方式；默认 JSON */
  responseType?: 'json' | 'blob'
}

/** FastAPI 的 detail 可能是纯字符串、{error, detail, code, request_id} 对象或校验数组 */
export function parseErrorDetail(body: unknown, fallback: string): { message: string; code: string; requestId: string } {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return { message: detail, code: '', requestId: '' }
  const record = (detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : {}) as Record<string, unknown>
  const message = typeof record.error === 'string' ? record.error : typeof record.detail === 'string' ? record.detail : fallback
  return { message, code: typeof record.code === 'string' ? record.code : '', requestId: typeof record.request_id === 'string' ? record.request_id : '' }
}

/** 幂等 GET 在网络层失败（status 0）或网关错误（502+）时允许重试一次；非 GET 一律不重试 */
export const RETRY_BACKOFF_MS = 500
export function retryableIdempotent(method: string | undefined, status: number): boolean {
  return (method || 'GET').toUpperCase() === 'GET' && (status === 0 || status >= 502)
}
export const backoff = (ms = RETRY_BACKOFF_MS) => new Promise<void>(resolve => setTimeout(resolve, ms))
