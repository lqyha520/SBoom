import { imageBlob, type WorksheetImage } from './image-generation'
import { MAX_WORKSHEET_IMAGES, MAX_WORKSHEET_ZIP_BYTES } from './generation-limits'
import { watermarkImage, type ImageWatermark } from './image-watermark'

/** Keep the original PNG bytes and batch page numbers, including gaps in a restored batch. */
export async function buildWorksheetImagesZip(images: readonly (WorksheetImage | null)[], progress: (done: number) => void = () => {}, cancelled: () => boolean = () => false, watermark?: ImageWatermark): Promise<Blob> {
  if (!images.some(Boolean) || images.length > MAX_WORKSHEET_IMAGES) throw new Error(`请选择 1 至 ${MAX_WORKSHEET_IMAGES} 张已生成的图片`)
  const checkCancelled = () => { if (cancelled()) throw new Error('已停止导出') }
  checkCancelled()
  if (images.reduce((size, image) => size + (image ? imageBlob(image).size : 0), 0) > MAX_WORKSHEET_ZIP_BYTES) {
    throw new Error('图片合计超过 128 MB，请缩小下载范围后分批下载')
  }
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip()
  let done = 0, outputBytes = 0
  for (const [index, image] of images.entries()) {
    checkCancelled()
    if (!image) continue
    const output = await watermarkImage(imageBlob(image), watermark, cancelled)
    outputBytes += output.size
    if (outputBytes > MAX_WORKSHEET_ZIP_BYTES) throw new Error('图片合计超过 128 MB，请缩小下载范围后分批下载')
    const bytes = new Uint8Array(await output.arrayBuffer())
    checkCancelled()
    zip.file(`习题图片-第${String(index + 1).padStart(Math.max(2, String(images.length).length), '0')}张.png`, bytes)
    progress(++done)
  }
  // PNG is already compressed. STORE preserves the originals without expensive recompression.
  checkCancelled()
  const blob = await zip.generateAsync({ type: 'blob', compression: 'STORE', streamFiles: true }, checkCancelled)
  checkCancelled()
  return blob
}
