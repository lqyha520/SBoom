import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { catalogDetail, type CatalogDetail, type CatalogPaper } from './catalog'
import { previewCatalog } from './experience'

/** 预览使用独立请求序列，不会互相取消来源搜索。 */
export function useCatalogPreview() {
  const preview = ref<CatalogDetail | null>(null), previewTarget = ref<CatalogPaper | null>(null)
  const previewRole = ref('admin'), previewOpen = ref(false), previewLoading = ref(false), previewError = ref(''), previewPages = ref(4)
  let sequence = 0
  async function showPreview(item: CatalogPaper, role = 'admin') {
    previewRole.value = role; previewTarget.value = item; preview.value = null
    previewPages.value = 4; previewError.value = ''; previewOpen.value = true; previewLoading.value = true
    const current = ++sequence
    try { const value = await (role === 'admin' ? catalogDetail(item.id) : previewCatalog(item.id, role)); if (current === sequence) preview.value = value }
    catch (cause) { if (current === sequence) previewError.value = cause instanceof Error ? cause.message : '预览加载失败' }
    finally { if (current === sequence) previewLoading.value = false }
  }
  const close = () => { sequence++; previewOpen.value = false; previewLoading.value = false }
  watch(previewOpen, open => { if (!open) { sequence++; previewLoading.value = false } })
  onDeactivated(close); onBeforeUnmount(close)
  return { preview, previewTarget, previewRole, previewOpen, previewLoading, previewError, previewPages, showPreview }
}
