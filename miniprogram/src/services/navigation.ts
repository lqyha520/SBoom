import { reactive } from 'vue'
import { safeDestination } from './return-route'

export interface CatalogFilters { q: string; grade: string; subject: string; category: string; topic: string }
export function catalogFilters(filters: Partial<CatalogFilters> = {}): CatalogFilters {
  return { q: (filters.q || '').trim().slice(0, 120), grade: filters.grade || '', subject: filters.subject || '', category: filters.category || '', topic: filters.topic || '' }
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

export function visitDestination(target: string, replace = false) {
  const destination = safeDestination(target)
  const [path, query = ''] = destination.split('?')
  if (path === '/pages/library/index' && query) {
    const filters: Partial<CatalogFilters> = {}
    for (const pair of query.split('&')) {
      const [key, value = ''] = pair.split('=')
      if (['q', 'grade', 'subject', 'category', 'topic'].includes(key || '')) filters[key as keyof CatalogFilters] = decodeURIComponent(value)
    }
    openCatalog(filters); return
  }
  if (['/pages/home/index', '/pages/library/index', '/pages/favorites/index', '/pages/account/index'].includes(path!)) uni.switchTab({ url: path! })
  else if (replace) uni.redirectTo({ url: destination })
  else uni.navigateTo({ url: destination })
}

export function confirmAction(title: string, content: string): Promise<boolean> {
  return new Promise(resolve => uni.showModal({ title, content, confirmText: '确认', cancelText: '取消', success: result => resolve(result.confirm), fail: () => resolve(false) }))
}
