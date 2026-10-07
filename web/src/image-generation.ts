import { request, type GenerationStatus } from './api'
import type { Difficulty } from './types'

export interface ImageWorksheetParams {
  grade: string
  subject: string
  keyword: string
  difficulty: Difficulty
  items: { game_type: string; question_count?: number | null }[]
  style: 'playful' | 'clean' | 'black_white'
  requirements: string
  image_count?: number
  image_index?: number
}
export interface WorksheetImage {
  request_id: string
  b64_json?: string
  blob?: Blob
  url?: string
  asset_id?: string
  expires_at?: number
  mime_type: 'image/png'
  width: number
  height: number
  prompt: string
}
export type ImageGenerationStatus = Omit<GenerationStatus, 'result'> & { kind: string; result: WorksheetImage | null }
const jsonHeaders = { 'Content-Type': 'application/json' }
export const fetchImageOptions = () => request<{ configured: boolean }>('/api/v1/image-generation/options')
export const previewImagePrompt = (params: ImageWorksheetParams) => request<{ prompt: string }>('/api/v1/image-generation/prompt', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(params) })
export const generateWorksheetImage = (params: ImageWorksheetParams, requestId: string) => request<WorksheetImage>('/api/v1/generate-image', {
  method: 'POST', headers: { ...jsonHeaders, 'X-Request-ID': requestId }, body: JSON.stringify(params),
}, 630_000)
export const fetchImageStatus = (requestId: string) => request<ImageGenerationStatus>('/api/v1/me/generations/' + encodeURIComponent(requestId))

export function plannedImageQuestionCount(items: ImageWorksheetParams['items']): number | undefined {
  return items.length && items.every(item => item.question_count != null)
    ? items.reduce((sum, item) => sum + item.question_count!, 0)
    : undefined
}

export function imageWorksheetTitle(params: ImageWorksheetParams): string {
  return `${params.grade}${params.subject}·${params.keyword.trim() || '年级知识练习'}`
}

export function imageBlob(image: WorksheetImage): Blob {
  if (image.blob instanceof Blob && image.blob.type === 'image/png' && image.blob.size <= 12 * 1024 * 1024) return image.blob
  if (image.mime_type !== 'image/png' || !image.b64_json || image.b64_json.length > 17_000_000) throw new Error('图片数据无效')
  const decoded = atob(image.b64_json)
  const bytes = new Uint8Array(decoded.length)
  for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i)
  return new Blob([bytes], { type: 'image/png' })
}


export async function loadImageBlob(image: WorksheetImage): Promise<Blob> {
  if (image.blob || image.b64_json) return imageBlob(image)
  if (!image.url || !/^\/api\/v1\/image-generation\/assets\/[a-f0-9]{32}$/.test(image.url)) throw new Error('图片地址无效')
  const blob = await request<Blob>(image.url, undefined, 60_000, 'blob')
  if (blob.type !== 'image/png' || blob.size > 12 * 1024 * 1024) throw new Error('图片数据无效')
  return blob
}
