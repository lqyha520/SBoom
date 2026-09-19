import { computed, reactive, ref } from 'vue'
// crypto.randomUUID 是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId } from '../../shared/webcrypto'

export const MAX_IMAGE_PAGES = 40
const MAX_IMAGE_BYTES = 20 * 1024 * 1024
const MAX_TOTAL_BYTES = 200 * 1024 * 1024
const MAX_PDF_BYTES = 32 * 1024 * 1024
export interface ImagePage {
  id: string; file: File; preview: string; width: number; height: number; rotation: number; error: string
}
export function imageFileIssue(file: File) {
  if (!/\.(jpe?g|png|webp)$/i.test(file.name)) return '仅支持 JPG、PNG、WebP 图片'
  if (!file.size) return '图片为空，请重新选择'
  if (file.size > MAX_IMAGE_BYTES) return '单张图片不能超过 20 MB'
  return ''
}
export function imagePageLayout(width: number, height: number) {
  if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))) throw new Error('图片尺寸无效')
  const landscape = width > height
  const pageWidth = landscape ? 297 : 210, pageHeight = landscape ? 210 : 297
  const scale = Math.min((pageWidth - 10) / width, (pageHeight - 10) / height)
  return { orientation: landscape ? 'landscape' as const : 'portrait' as const,
    x: (pageWidth - width * scale) / 2, y: (pageHeight - height * scale) / 2, width: width * scale, height: height * scale }
}
async function readImage(file: File) {
  const issue = imageFileIssue(file)
  if (issue) throw new Error(issue)
  let bitmap: ImageBitmap
  try { bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' }) }
  catch { throw new Error('图片无法读取，请检查文件是否损坏或转为 JPG/PNG') }
  if (!bitmap.width || !bitmap.height || bitmap.width * bitmap.height > 50_000_000) {
    bitmap.close(); throw new Error('图片尺寸过大或无效，请缩小到 5000 万像素以内')
  }
  return bitmap
}
async function renderImage(bitmap: ImageBitmap, rotation: number, maxSide: number) {
  const turned = rotation % 180 !== 0
  const width = turned ? bitmap.height : bitmap.width, height = turned ? bitmap.width : bitmap.height
  const scale = Math.min(1, maxSide / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale)); canvas.height = Math.max(1, Math.round(height * scale))
  try {
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('当前浏览器无法处理图片，请使用新版浏览器')
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high'
    ctx.translate(canvas.width / 2, canvas.height / 2); ctx.rotate(rotation * Math.PI / 180)
    ctx.drawImage(bitmap, -bitmap.width * scale / 2, -bitmap.height * scale / 2, bitmap.width * scale, bitmap.height * scale)
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('图片转换失败')), 'image/jpeg', 0.94))
    return { blob, width: canvas.width, height: canvas.height }
  } finally { canvas.width = 0; canvas.height = 0 }
}
export async function buildImagePdf(pages: readonly ImagePage[], title: string, progress: (done: number) => void, cancelled: () => boolean) {
  if (!pages.length || pages.length > MAX_IMAGE_PAGES) throw new Error('请选择 1 至 40 张图片')
  if (pages.some(page => page.error)) throw new Error('请先移除无法读取的图片')
  if (!title.trim()) throw new Error('请填写公开标题')
  const { jsPDF } = await import('jspdf')
  let pdf: InstanceType<typeof jsPDF> | undefined, encodedBytes = 0
  for (const [index, page] of pages.entries()) {
    if (cancelled()) throw new Error('已停止合并，图片清单已保留')
    const bitmap = await readImage(page.file)
    try {
      const rendered = await renderImage(bitmap, page.rotation, 3508)
      if (cancelled()) throw new Error('已停止合并，图片清单已保留')
      encodedBytes += rendered.blob.size
      if (encodedBytes > MAX_PDF_BYTES) throw new Error('合并后的 PDF 超过 32 MB，请减少图片或压缩后重试')
      const layout = imagePageLayout(rendered.width, rendered.height)
      if (!pdf) pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: layout.orientation, compress: true })
      else pdf.addPage('a4', layout.orientation)
      pdf.addImage(new Uint8Array(await rendered.blob.arrayBuffer()), 'JPEG', layout.x, layout.y, layout.width, layout.height)
      progress(index + 1)
    } finally { bitmap.close() }
    await new Promise(resolve => setTimeout(resolve, 0))
  }
  if (cancelled()) throw new Error('已停止合并，图片清单已保留')
  const blob = pdf!.output('blob')
  if (blob.size > MAX_PDF_BYTES) throw new Error('合并后的 PDF 超过 32 MB，请减少图片或压缩后重试')
  const name = title.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/\.pdf$/i, '').slice(0, 160) || '图片习题'
  return new File([blob], name + '.pdf', { type: 'application/pdf' })
}
export function useImagePdfComposer() {
  const pages = ref<ImagePage[]>([]), title = ref(''), busy = ref(false), progress = ref(''), error = ref('')
  let revision = 0, disposed = false
  const ready = computed(() => !!pages.value.length && !pages.value.some(page => page.error) && !!title.value.trim() && !busy.value)
  async function add(files: File[]) {
    if (busy.value || disposed) return
    const current = ++revision
    busy.value = true; error.value = ''; progress.value = '正在读取图片'
    try {
      let bytes = pages.value.reduce((sum, page) => sum + page.file.size, 0)
      for (const file of files) {
        if (disposed || current !== revision) break
        if (pages.value.length >= MAX_IMAGE_PAGES) { error.value = '最多合并 40 张图片，其余图片未添加'; break }
        if (bytes + file.size > MAX_TOTAL_BYTES) { error.value = '图片总大小不能超过 200 MB，其余图片未添加'; break }
        const page = reactive<ImagePage>({ id: randomId(), file, preview: '', width: 0, height: 0, rotation: 0, error: '' })
        try {
          const bitmap = await readImage(file)
          try {
            page.width = bitmap.width; page.height = bitmap.height
            const thumbnail = await renderImage(bitmap, 0, 320)
            if (disposed || current !== revision) break
            page.preview = URL.createObjectURL(thumbnail.blob)
          } finally { bitmap.close() }
        } catch (cause) { page.error = cause instanceof Error ? cause.message : '图片读取失败' }
        if (disposed || current !== revision) { if (page.preview) URL.revokeObjectURL(page.preview); break }
        pages.value.push(page); bytes += file.size
        if (!title.value) title.value = file.name.replace(/\.[^.]+$/, '').slice(0, 240)
      }
    } finally { busy.value = false; progress.value = '' }
  }
  function remove(id: string) {
    if (busy.value) return
    const page = pages.value.find(value => value.id === id)
    if (page?.preview) URL.revokeObjectURL(page.preview)
    pages.value = pages.value.filter(value => value.id !== id); error.value = ''
  }
  function move(index: number, offset: number) {
    const next = index + offset
    if (busy.value || index < 0 || index >= pages.value.length || next < 0 || next >= pages.value.length) return
    const [page] = pages.value.splice(index, 1); pages.value.splice(next, 0, page)
  }
  function rotate(id: string) {
    const page = pages.value.find(value => value.id === id)
    if (!busy.value && page) page.rotation = (page.rotation + 90) % 360
  }
  async function build() {
    if (!ready.value || disposed) return
    const current = ++revision
    busy.value = true; error.value = ''; progress.value = `正在合并 0/${pages.value.length} 页`
    try {
      return await buildImagePdf([...pages.value], title.value, done => { progress.value = `正在合并 ${done}/${pages.value.length} 页` }, () => disposed || revision !== current)
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '图片合并失败' }
    finally { busy.value = false; progress.value = '' }
  }
  function clear() {
    if (busy.value) return
    pages.value.forEach(page => { if (page.preview) URL.revokeObjectURL(page.preview) })
    pages.value = []; title.value = ''; error.value = ''
  }
  function cancel() { revision++ }
  function dispose() { disposed = true; cancel(); pages.value.forEach(page => { if (page.preview) URL.revokeObjectURL(page.preview) }); pages.value = [] }
  return reactive({ pages, title, busy, progress, error, ready, add, remove, move, rotate, build, clear, cancel, dispose })
}
export type ImagePdfComposer = ReturnType<typeof useImagePdfComposer>
