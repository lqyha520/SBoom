import { reactive } from 'vue'
import { routeFromPage, safeDestination } from './return-route'

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

/**
 * 登录页是 navigateTo 进来的，上一页通常就是 returnTo 指向的那一页。
 * 这时必须退栈而不是再压一层，否则页面栈里会留下两份同样的页面，用户点返回会重复看到它。
 */
function backToPrevious(destination: string) {
  if (typeof getCurrentPages !== 'function') return false
  const pages = getCurrentPages()
  if (pages.length < 2) return false
  if (routeFromPage(pages[pages.length - 2] as unknown as Parameters<typeof routeFromPage>[0]) !== destination) return false
  uni.navigateBack({ delta: 1, fail: () => uni.redirectTo({ url: destination }) })
  return true
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
  else if (replace) { if (!backToPrevious(destination)) uni.redirectTo({ url: destination }) }
  else uni.navigateTo({ url: destination })
}

export function confirmAction(title: string, content: string): Promise<boolean> {
  return new Promise(resolve => uni.showModal({ title, content, confirmText: '确认', cancelText: '取消', success: result => resolve(result.confirm), fail: () => resolve(false) }))
}
