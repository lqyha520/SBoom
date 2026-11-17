import { request } from './api'
import type { ArchiveDetail } from './library'
import { plannedImageQuestionCount, type ImageWorksheetParams, type WorksheetImage } from './image-generation'
import { sha256Hex } from '../../shared/webcrypto'
import { MAX_WORKSHEET_PDF_PAGES, MAX_WORKSHEET_PDF_BYTES } from './generation-limits'

export async function imageCloudRequestId(images: readonly WorksheetImage[]): Promise<string> {
  if (!images.length || images.length > MAX_WORKSHEET_PDF_PAGES) throw new Error(`一份云端 PDF 支持 1 至 ${MAX_WORKSHEET_PDF_PAGES} 张图片，请缩小保存范围`)
  return sha256Hex(new TextEncoder().encode(JSON.stringify(images.map(image => image.request_id))))
}

export function saveImageArchive(pdf: Blob, requestId: string, title: string, params: ImageWorksheetParams, imageCount: number, folderId: string | null, signal?: AbortSignal) {
  if (!Number.isInteger(imageCount) || imageCount < 1 || imageCount > MAX_WORKSHEET_PDF_PAGES) throw new Error(`请选择 1 至 ${MAX_WORKSHEET_PDF_PAGES} 张图片保存`)
  if (!pdf.size || pdf.type !== 'application/pdf') throw new Error('PDF 文件无效，请重新合成')
  if (pdf.size > MAX_WORKSHEET_PDF_BYTES) throw new Error('云端文件不能超过 32 MB，请缩小保存范围后分批保存')
  const count = plannedImageQuestionCount(params.items)
  const query = new URLSearchParams({ request_id: requestId, title, grade: params.grade, subject: params.subject,
    keyword: params.keyword, question_types: params.items.map(item => item.game_type).join(',') })
  if (count !== undefined) query.set('question_count', String(count * imageCount))
  if (folderId) query.set('folder_id', folderId)
  return request<ArchiveDetail>('/api/v1/library/import?' + query, {
    method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: pdf, signal,
  }, 120_000)
}
