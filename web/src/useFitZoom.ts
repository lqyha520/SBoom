import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/** 容器宽度自适应缩放：A4 纸(约800px)放不进容器时整体缩小 */
export function useFitZoom(container: Ref<HTMLElement | null>, targetWidth = 800) {
  const zoom = ref(1)
  let ro: ResizeObserver | null = null

  function update() {
    const el = container.value
    if (!el) return
    zoom.value = Math.min(1, Math.max(0.35, (el.clientWidth - 36) / targetWidth))
  }

  onMounted(() => {
    update()
    ro = new ResizeObserver(update)
    if (container.value) ro.observe(container.value)
  })
  onBeforeUnmount(() => ro?.disconnect())

  return zoom
}
