import { request } from './api'
import type { ApiSchemas } from '../../shared/api-schema'

export interface ImageModelConfig {
  revision?: string
  baseUrl: string
  model: string
  timeout: number
  size: string
  responseFormat: 'auto' | 'b64_json' | 'url'
  requestMode?: 'auto' | 'sync' | 'async'
  hasKey: boolean
  models?: ImageModelProfile[]
}
export type ImageModelProfile = Omit<ApiSchemas['ImageModelProfile'], 'apiKey'> & { hasKey: boolean }
const endpoint = '/api/v1/admin/image-config'
export const fetchImageConfig = () => request<ImageModelConfig>(endpoint)
export const saveImageConfig = (config: ApiSchemas['ImageModelProfiles']) =>
  request<ImageModelConfig>(endpoint, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) })
export const clearImageConfig = (revision?: string) =>
  request<ImageModelConfig>(endpoint, { method: 'DELETE', headers: revision ? { 'If-Match': revision } : {} })
