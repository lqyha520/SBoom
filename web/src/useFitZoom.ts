import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * 容器宽度自适应缩放：A4 纸缩到容器宽度放得下，高度不限（滚动浏览）。
 * 用户可通过 slider 覆盖（0 = 自动）。
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
    auto.value = Math.min(1, Math.max(0.25, (el.clientWidth - 24) / PAPER_W))
    apply()
  }

  function apply() {
    zoom.value = manual.value > 0 ? manual.value : auto.value
  }

  function setManual(v: number) {
    manual.value = v
    apply()
  }

  onMounted(() => {
    update()
    ro = new ResizeObserver(update)
    if (container.value) ro.observe(container.value)
  })
  onBeforeUnmount(() => ro?.disconnect())

  return { zoom, manual, setManual }
}
