import { request } from './api'

export interface ImageModelConfig {
  baseUrl: string
  model: string
  timeout: number
  size: string
  responseFormat: 'auto' | 'b64_json' | 'url'
  hasKey: boolean
}
const endpoint = '/api/v1/admin/image-config'
export const fetchImageConfig = () => request<ImageModelConfig>(endpoint)
export const saveImageConfig = (config: Omit<ImageModelConfig, 'hasKey'> & { apiKey: string }) =>
  request<ImageModelConfig>(endpoint, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) })
export const clearImageConfig = () => request(endpoint, { method: 'DELETE' })
