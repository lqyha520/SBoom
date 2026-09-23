import { imageBlob, type WorksheetImage } from './image-generation'

/** Keep each complete image on its own A4 page, with the original aspect ratio. */
export async function buildWorksheetPdf(images: readonly WorksheetImage[], progress: (done: number) => void = () => {}, cancelled: () => boolean = () => false): Promise<Blob> {
  if (!images.length || images.length > 10) throw new Error('请选择 1 至 10 张已生成的图片')
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true })
  for (const [index, image] of images.entries()) {
    if (cancelled()) throw new Error('已停止导出')
    const bytes = new Uint8Array(await imageBlob(image).arrayBuffer())
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
  return pdf.output('blob')
}
