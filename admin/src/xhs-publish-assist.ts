import { localFetch } from './local-access'
import type { PublicationMedia } from './xhs-media-cache'

export const ASSIST_BRIDGE = 'http://127.0.0.1:17632'
export interface AssistSession { account_id: string; token: string; record_id: string; revision: number; status: 'waiting' | 'filling' | 'prepared' | 'paused'; message: string; browser_open: boolean; touched: boolean }
export interface AssistState { available: boolean; busy: boolean; session: AssistSession | null }
export interface AssistMedia { file: File; url: string; reference?: PublicationMedia }
const MB = 1024 * 1024
export function validateMedia(files: Pick<File, 'type' | 'size'>[]) {
  if (!files.length || files.length > 9) throw new Error('请选择 1–9 张图片，或 1 个 MP4 视频。')
  const video = files.some(file => file.type === 'video/mp4')
  if (video && files.length !== 1) throw new Error('视频只能单独选择一个，不能与图片混用。')
  for (const file of files) {
    if (!['image/png', 'image/jpeg', 'image/webp', 'video/mp4'].includes(file.type)) throw new Error('仅支持 PNG、JPEG、WebP 图片或 MP4 视频。')
    if (!file.size || file.size > (video ? 40 : 10) * MB) throw new Error('单张图片最多 10 MB，视频最多 40 MB，不能选择空文件。')
  }
  if (files.reduce((sum, file) => sum + file.size, 0) > (video ? 40 : 30) * MB) throw new Error('图片合计最多 30 MB，视频最多 40 MB。')
}
export const mediaBase64 = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result).split(',')[1]!)
  reader.onerror = () => reject(new Error('无法读取本机文件，请重新选择。'))
  reader.readAsDataURL(file)
})
export async function assistRequest<T = AssistState>(route: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await localFetch(ASSIST_BRIDGE + route, { method: body === undefined ? 'GET' : 'POST', mode: 'cors', credentials: 'omit', cache: 'no-store',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(60_000) })
  } catch (cause) { if (cause instanceof Error && 'code' in cause && cause.code === 'permission_denied') throw cause; throw new Error('无法连接本机辅助服务或请求超时。请检查本机服务与浏览器的本地网络权限，再点“查看辅助状态”；不要立即重复上传。') }
  const result = await response.json().catch(() => ({})) as T & { error?: string }
  if (!response.ok) throw new Error(result.error || '辅助请求失败，请检查本机服务。')
  return result
}
