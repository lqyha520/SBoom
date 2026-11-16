import { imageBlob, type WorksheetImage } from './image-generation'
import { MAX_WORKSHEET_PDF_PAGES, MAX_WORKSHEET_PDF_BYTES } from './generation-limits'
import { watermarkImage, type ImageWatermark } from './image-watermark'

/** Keep each complete image on its own A4 page, with the original aspect ratio. */
export async function buildWorksheetPdf(images: readonly WorksheetImage[], progress: (done: number) => void = () => {}, cancelled: () => boolean = () => false, watermark?: ImageWatermark): Promise<Blob> {
  if (!images.length || images.length > MAX_WORKSHEET_PDF_PAGES) throw new Error(`一份 PDF 支持 1 至 ${MAX_WORKSHEET_PDF_PAGES} 张图片，请缩小下载和保存范围`)
  if (cancelled()) throw new Error('已停止导出')
  if (images.reduce((size, image) => size + imageBlob(image).size, 0) > MAX_WORKSHEET_PDF_BYTES) {
    throw new Error('图片合计超过 32 MB，请缩小下载和保存范围后分批合成 PDF')
  }
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true })
  let outputBytes = 0
  for (const [index, image] of images.entries()) {
    if (cancelled()) throw new Error('已停止导出')
    const output = await watermarkImage(imageBlob(image), watermark, cancelled)
    outputBytes += output.size
    if (outputBytes > MAX_WORKSHEET_PDF_BYTES) throw new Error('图片合计超过 32 MB，请缩小下载和保存范围后分批合成 PDF')
    const bytes = new Uint8Array(await output.arrayBuffer())
    if (cancelled()) throw new Error('已停止导出')
    // Decode actual PNG dimensions instead of trusting cached metadata.
    const properties = pdf.getImageProperties(bytes)
    const { width, height } = properties
    if (!(width > 0 && height > 0) || width * height > 16_000_000) throw new Error('图片尺寸无效')
    const orientation = width > height ? 'landscape' : 'portrait'
    pdf.addPage('a4', orientation)
    const pageWidth = pdf.internal.pageSize.getWidth(), pageHeight = pdf.internal.pageSize.getHeight()
    const scale = Math.min((pageWidth - 10) / width, (pageHeight - 10) / height)
    pdf.addImage(bytes, 'PNG', (pageWidth - width * scale) / 2, (pageHeight - height * scale) / 2, width * scale, height * scale, `page-${index}`, 'FAST')
    progress(index + 1)
    await new Promise(resolve => setTimeout(resolve, 0))
  }
  if (cancelled()) throw new Error('已停止导出')
  pdf.deletePage(1)
  const blob = pdf.output('blob')
  if (blob.size > MAX_WORKSHEET_PDF_BYTES) throw new Error('PDF 超过 32 MB，请缩小下载和保存范围')
  return blob
}
