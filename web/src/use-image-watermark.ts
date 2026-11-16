import { computed, onMounted, ref, watch, type Ref } from 'vue'
import { imageBlob, type WorksheetImage } from './image-generation'
import {
  DEFAULT_WATERMARK_TRANSPARENCY,
  MAX_WATERMARK_TEXT_LENGTH,
  WATERMARK_LAYOUTS,
  WATERMARK_POSITIONS,
  watermarkImage,
  watermarkText,
  type ImageWatermark,
  type WatermarkLayout,
  type WatermarkPosition
} from './image-watermark'

/** 水印偏好按账号保存；换图、退出或卸载会停止旧预览并释放对象地址。 */
export function useImageWatermark(
  result: Readonly<Ref<WorksheetImage | null | undefined>>,
  storageKey: string,
  current: () => boolean
) {
  let loaded = false
  const watermarkEnabled = ref(false),
    watermarkLabel = ref('')
  const watermarkPosition = ref<WatermarkPosition>('bottom-right')
  const watermarkLayout = ref<WatermarkLayout>('single'),
    watermarkTransparency = ref(DEFAULT_WATERMARK_TRANSPARENCY)
  const watermarkKey = storageKey + '_watermark'
  const watermarkPreview = ref(''),
    watermarkPreviewBusy = ref(false),
    watermarkPreviewError = ref('')
  const watermarkIssue = computed(() => {
    if (!watermarkEnabled.value) return ''
    try {
      watermarkText(watermarkLabel.value)
      return ''
    } catch (cause) {
      return (cause as Error).message
    }
  })
  const downloadWatermark = computed<ImageWatermark | undefined>(() =>
    watermarkEnabled.value && !watermarkIssue.value
      ? {
          text: watermarkText(watermarkLabel.value),
          position: watermarkPosition.value,
          layout: watermarkLayout.value,
          opacity: (100 - watermarkTransparency.value) / 100
        }
      : undefined
  )
  watch([result, downloadWatermark, () => current()], ([image, watermark], _, onCleanup) => {
    let stopped = false,
      url = ''
    watermarkPreview.value = ''
    watermarkPreviewError.value = ''
    watermarkPreviewBusy.value = false
    if (!image || !watermark || !current()) return
    watermarkPreviewBusy.value = true
    const timer = setTimeout(async () => {
      try {
        const blob = await watermarkImage(imageBlob(image), watermark, () => stopped || !current())
        if (stopped || !current()) return
        url = URL.createObjectURL(blob)
        watermarkPreview.value = url
      } catch (cause) {
        if (!stopped && current())
          watermarkPreviewError.value = cause instanceof Error ? cause.message : '水印预览失败，请重试'
      } finally {
        if (!stopped && current()) watermarkPreviewBusy.value = false
      }
    }, 250)
    onCleanup(() => {
      stopped = true
      clearTimeout(timer)
      if (url) URL.revokeObjectURL(url)
    })
  })
  watch([watermarkEnabled, watermarkLabel, watermarkPosition, watermarkLayout, watermarkTransparency], () => {
    if (!current() || !loaded) return
    try {
      localStorage.setItem(
        watermarkKey,
        JSON.stringify({
          enabled: watermarkEnabled.value,
          text: watermarkLabel.value,
          position: watermarkPosition.value,
          layout: watermarkLayout.value,
          transparency: watermarkTransparency.value
        })
      )
    } catch {
      /* 偏好保存失败不影响本次下载。 */
    }
  })
  onMounted(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(watermarkKey) || 'null')
      if (saved && typeof saved.text === 'string') {
        watermarkLabel.value = saved.text.slice(0, MAX_WATERMARK_TEXT_LENGTH)
        watermarkEnabled.value = saved.enabled === true
        watermarkPosition.value =
          WATERMARK_POSITIONS.find((item) => item.value === saved.position)?.value || 'bottom-right'
        watermarkLayout.value = WATERMARK_LAYOUTS.find((item) => item.value === saved.layout)?.value || 'single'
        if (Number.isInteger(saved.transparency) && saved.transparency >= 0 && saved.transparency <= 100)
          watermarkTransparency.value = saved.transparency
      }
    } catch {
      /* 忽略损坏的水印偏好。 */
    }
    loaded = true
  })
  return {
    watermarkEnabled,
    watermarkLabel,
    watermarkPosition,
    watermarkLayout,
    watermarkTransparency,
    watermarkIssue,
    downloadWatermark,
    watermarkPreview,
    watermarkPreviewBusy,
    watermarkPreviewError
  }
}
