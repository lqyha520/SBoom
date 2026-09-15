import { reactive } from 'vue'

export interface CatalogFilters { q: string; grade: string; subject: string; category: string }
export function catalogFilters(filters: Partial<CatalogFilters> = {}): CatalogFilters {
  return { q: (filters.q || '').trim().slice(0, 120), grade: filters.grade || '', subject: filters.subject || '', category: filters.category || '' }
}
export const catalogSelection = reactive({ ...catalogFilters(), revision: 0 })
export function openCatalog(filters: Partial<CatalogFilters> = {}) {
  // switchTab drops query parameters, so the list consumes a fresh selection on show.
  Object.assign(catalogSelection, catalogFilters(filters), { revision: catalogSelection.revision + 1 })
  uni.switchTab({ url: '/pages/library/index' })
}
export function openCatalogPaper(id: string) {
  uni.navigateTo({ url: '/pages/paper/index?id=' + encodeURIComponent(id) + '&scope=catalog' })
}

export function confirmAction(title: string, content: string): Promise<boolean> {
  return new Promise(resolve => uni.showModal({ title, content, confirmText: '确认', cancelText: '取消', success: result => resolve(result.confirm), fail: () => resolve(false) }))
}
