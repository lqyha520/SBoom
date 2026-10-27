import type { GlobalLlmConfig } from './api'
import type { ImageModelConfig } from './image-api'
import { randomId } from '../../shared/webcrypto'

export type ModelKind = 'text' | 'image'
export interface ModelDraft {
  id: string
  name: string
  enabled: boolean
  hasKey: boolean
  baseUrl: string
  model: string
  apiKey: string
  timeout: number
  maxTokens: number
  samplingMode: 'configured' | 'omit'
  tokenParameter: 'max_tokens' | 'max_completion_tokens'
  size: string
  responseFormat: ImageModelConfig['responseFormat']
  requestMode: 'auto' | 'sync' | 'async'
}

export function newModel(kind: ModelKind): ModelDraft {
  return {
    id: randomId(), name: '', enabled: true, hasKey: false,
    baseUrl: '', model: '', apiKey: '', timeout: kind === 'text' ? 120 : 300,
    maxTokens: 16384, samplingMode: 'configured', tokenParameter: 'max_tokens',
    size: '1024x1536', responseFormat: 'auto', requestMode: 'auto',
  }
}

export function modelDrafts(value: GlobalLlmConfig | ImageModelConfig, kind: ModelKind): ModelDraft[] {
  const profiles = value.models ?? (value.baseUrl || value.model || value.hasKey
    ? [{ ...value, id: 'legacy', name: '', enabled: true }] : [])
  return profiles.map(profile => ({ ...newModel(kind), ...profile, apiKey: '' }))
}

export function textPayload(profiles: ModelDraft[], revision = '') {
  return { revision, models: profiles.map(profile => ({
    id: profile.id, name: profile.name.trim(), enabled: profile.enabled,
    baseUrl: profile.baseUrl.trim(), model: profile.model.trim(), apiKey: profile.apiKey.trim(),
    timeout: profile.timeout, maxTokens: profile.maxTokens,
    samplingMode: profile.samplingMode, tokenParameter: profile.tokenParameter,
  })) }
}

export function imagePayload(profiles: ModelDraft[], revision = '') {
  return { revision, models: profiles.map(profile => ({
    id: profile.id, name: profile.name.trim(), enabled: profile.enabled,
    baseUrl: profile.baseUrl.trim(), model: profile.model.trim(), apiKey: profile.apiKey.trim(),
    timeout: profile.timeout, size: profile.size.trim(), responseFormat: profile.responseFormat, requestMode: profile.requestMode,
  })) }
}

export function modelError(profile: ModelDraft, kind: ModelKind, testing = false): string {
  const endpoint = profile.baseUrl.trim()
  try {
    const url = new URL(endpoint)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.port === '0' || /\s/.test(endpoint)) throw new Error()
  } catch { return '接口地址无效，不能包含账号、查询参数或片段' }
  if (endpoint.length > 500 || !profile.model.trim() || profile.model.trim().length > 120) return '请填写有效的接口地址和模型名称'
  if (!Number.isInteger(profile.timeout) || profile.timeout < (kind === 'image' ? 30 : 10) || profile.timeout > 600) return `超时时间须为 ${kind === 'image' ? 30 : 10} 至 600 的整数`
  if (profile.apiKey.trim().length > 4000 || ((testing || profile.enabled) && !profile.hasKey && !profile.apiKey.trim())) return '请填写此模型的 API 密钥'
  if (kind === 'text' && (!Number.isInteger(profile.maxTokens) || profile.maxTokens < 1024 || profile.maxTokens > 131072)) return '最大输出 token 须为 1024 至 131072 的整数'
  if (kind === 'image' && profile.size.trim() !== 'auto' && !/^[1-9]\d{2,3}x[1-9]\d{2,3}$/.test(profile.size.trim())) return '图片尺寸须为宽x高（如 1024x1536）或 auto'
  return ''
}
