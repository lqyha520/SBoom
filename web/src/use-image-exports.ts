import { computed, ref, type Ref } from 'vue'
import { imageBlob, type WorksheetImage } from './image-generation'
import { watermarkImage, type ImageWatermark } from './image-watermark'
import { downloadBlob, triggerDownload } from '../../shared/download'

type Read<T> = Readonly<Ref<T>>
interface ExportContext {
  imageUrl: Read<string>
  result: Read<WorksheetImage | null | undefined>
  selectedPage: Read<number>
  rangePages: Read<(WorksheetImage | null)[]>
  rangeImages: Read<WorksheetImage[]>
  exportCount: Read<number>
  busy: Read<boolean>
  checking: Read<boolean>
  dialogOpen: Read<boolean>
  watermarkIssue: Read<string>
  downloadWatermark: Read<ImageWatermark | undefined>
  error: Ref<string>
  current: () => boolean
  ownerGuard: () => void
}
/** 下载使用发起时的图片与水印快照；账号变化后丢弃迟到结果。 */
export function useImageExports(context: ExportContext) {
  const {
    imageUrl,
    result,
    selectedPage,
    rangePages,
    rangeImages,
    exportCount,
    busy,
    checking,
    dialogOpen,
    watermarkIssue,
    downloadWatermark,
    error,
    current,
    ownerGuard
  } = context
  const pdfBusy = ref(false),
    pdfProgress = ref('')
  const imagesBusy = ref(false),
    imagesProgress = ref('')
  const singleBusy = ref(false)
  const exportBusy = computed(() => pdfBusy.value || imagesBusy.value || singleBusy.value)
  function downloadFile(url: string, name: string) {
    triggerDownload(url, name)
  }
  async function download() {
    if (!imageUrl.value || !result.value || !current() || exportBusy.value || watermarkIssue.value) return
    const image = result.value,
      watermark = downloadWatermark.value
    const name = `习题图片-${image.request_id.slice(0, 8)}-第${selectedPage.value + 1}张.png`
    if (!watermark) {
      downloadFile(imageUrl.value, name)
      return
    }
    singleBusy.value = true
    error.value = ''
    try {
      const blob = await watermarkImage(imageBlob(image), watermark, () => !current())
      ownerGuard()
      if (current()) downloadBlob(blob, name)
    } catch (cause) {
      if (current()) error.value = cause instanceof Error ? cause.message : '图片下载失败，请重试'
    } finally {
      singleBusy.value = false
    }
  }
  async function downloadImages() {
    if (
      !current() ||
      exportBusy.value ||
      busy.value ||
      checking.value ||
      dialogOpen.value ||
      !exportCount.value ||
      watermarkIssue.value
    )
      return
    const images = [...rangePages.value]
    const watermark = downloadWatermark.value
    const completed = images.filter((image): image is WorksheetImage => !!image)
    imagesBusy.value = true
    error.value = ''
    imagesProgress.value = `正在打包 0 / ${completed.length} 张`
    try {
      const { buildWorksheetImagesZip } = await import('./worksheet-images')
      const blob = await buildWorksheetImagesZip(
        images,
        (done) => {
          if (current()) imagesProgress.value = `正在打包 ${done} / ${completed.length} 张`
        },
        () => !current(),
        watermark
      )
      ownerGuard()
      if (!current()) return
      downloadBlob(blob, `习题图片-${completed[0].request_id.slice(0, 8)}-${completed.length}张.zip`)
    } catch (cause) {
      if (current()) error.value = cause instanceof Error ? cause.message : '图片打包失败，已生成的图片仍可逐张下载'
    } finally {
      imagesBusy.value = false
      imagesProgress.value = ''
    }
  }
  async function downloadPdf() {
    if (
      !current() ||
      exportBusy.value ||
      busy.value ||
      checking.value ||
      dialogOpen.value ||
      !exportCount.value ||
      watermarkIssue.value
    )
      return
    const images = [...rangeImages.value]
    const watermark = downloadWatermark.value
    pdfBusy.value = true
    error.value = ''
    pdfProgress.value = `正在合并 0 / ${images.length} 页`
    try {
      const { buildWorksheetPdf } = await import('./worksheet-pdf')
      const blob = await buildWorksheetPdf(
        images,
        (done) => {
          if (current()) pdfProgress.value = `正在合并 ${done} / ${images.length} 页`
        },
        () => !current(),
        watermark
      )
      ownerGuard()
      if (!current()) return
      downloadBlob(blob, `习题图片-${images[0].request_id.slice(0, 8)}-${images.length}页.pdf`)
    } catch (cause) {
      if (current()) error.value = cause instanceof Error ? cause.message : 'PDF 导出失败，图片已保留'
    } finally {
      pdfBusy.value = false
      pdfProgress.value = ''
    }
  }
  return {
    pdfBusy,
    pdfProgress,
    imagesBusy,
    imagesProgress,
    singleBusy,
    exportBusy,
    download,
    downloadImages,
    downloadPdf
  }
}
