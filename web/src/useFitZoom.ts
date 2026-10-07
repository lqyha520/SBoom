import { onActivated, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

/**
 * 容器宽度自适应缩放：纸缩放到容器宽度放得下为止（上限 100% 原尺寸），
 * 高度不限（滚动浏览）。用户可通过 slider 覆盖（0 = 自动）。
 */
export function useFitZoom(container: Ref<HTMLElement | null>) {
  const auto = ref(1)
  /** 0 = 自动；>0 = 用户指定比例 */
  const manual = ref(0)
  const zoom = ref(1)
  let ro: ResizeObserver | null = null

  // A4 纸宽度约 794px + 边距
  const PAPER_W = 810

  function update() {
    const el = container.value
    if (!el) return
    if (!el.clientWidth) return
    const style = getComputedStyle(el)
    const padding = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0)
    auto.value = Math.min(1, Math.max(0.25, (el.clientWidth - padding - 12) / PAPER_W))
    apply()
  }

  function apply() {
    zoom.value = manual.value > 0 ? manual.value : auto.value
  }

  function setManual(v: number) {
    manual.value = !Number.isFinite(v) || v <= 0 ? 0 : Math.min(1, Math.max(0.25, v))
    apply()
  }

  onMounted(() => {
    ro = new ResizeObserver(update)
    watch(container, (element, previous) => {
      if (previous) ro?.disconnect()
      if (element) { ro?.observe(element); update() }
    }, { immediate: true, flush: 'post' })
  })
  onActivated(update)
  onBeforeUnmount(() => ro?.disconnect())

  return { zoom, manual, setManual }
}
