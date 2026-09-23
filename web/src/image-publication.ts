import { request } from './api'

export interface ImagePublicationMeta {
  keyword?: string
  question_types?: string
  question_count?: number
  title: string
  grade: string
  subject: string
  category_id: string
  description: string
}
export interface ImagePublication { id: string; title: string; status: string; page_count: number }
export interface PublicationCategory { id: string; name: string; is_visible: boolean }

export const fetchPublicationCategories = () => request<{ items: PublicationCategory[] }>('/api/v1/admin/site/categories')
export const publicationUrl = (id: string) => '/admin/#papers?paper=' + encodeURIComponent(id)

/** Use the existing PDF import pipeline to create a ready-to-preview catalog draft. */
export function addImagePublication(pdf: Blob, meta: ImagePublicationMeta) {
  if (!pdf.size || pdf.type !== 'application/pdf') throw new Error('PDF 文件无效，请重新合成')
  if (pdf.size > 32 * 1024 * 1024) throw new Error('PDF 超过 32 MB，请下载图片后在后台分批添加')
  const query = new URLSearchParams({ ...Object.fromEntries(Object.entries(meta).map(([key, value]) => [key, String(value)])), mode: 'student', download_mode: 'pdf', view_access: 'inherit', download_access: 'inherit' })
  return request<ImagePublication>('/api/v1/admin/catalog/import?' + query, {
    method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: pdf,
  }, 120_000)
}
