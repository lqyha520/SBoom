import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/** 容器自适应缩放：A4 纸完整显示在容器内（宽和高都适配） */
export function useFitZoom(container: Ref<HTMLElement | null>) {
  const zoom = ref(1)
  let ro: ResizeObserver | null = null

  // A4 全页（含卡片间距）原始尺寸约 800×1140px
  const PAPER_W = 810
  const PAPER_H = 1160

  function update() {
    const el = container.value
    if (!el) return
    const byW = (el.clientWidth - 24) / PAPER_W
    const byH = (el.clientHeight - 24) / PAPER_H
    // 宽度优先（横向布局的纸），但不小于高度约束，保证整页可见
    zoom.value = Math.min(1, Math.max(0.25, byW, Math.min(byW, byH)))
  }

  onMounted(() => {
    update()
    ro = new ResizeObserver(update)
    if (container.value) ro.observe(container.value)
  })
  onBeforeUnmount(() => ro?.disconnect())

  return zoom
}
