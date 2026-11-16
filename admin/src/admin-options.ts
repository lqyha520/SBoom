import { adminRoute } from './navigation'
import { canAdmin } from './permissions'

/** 当前菜单表单的关联选项，不赋予关联配置菜单的访问权。 */
export function optionPath(kind: string, owner: string, fallback: string) {
  if (adminRoute.tab === 'financeBills' && kind === 'payment' && !canAdmin(owner)) return '/api/v1/admin/options/reconciliations/payment'
  const scopes: Record<string, string[]> = {
    papers: ['categories', 'dictionary', 'tags'], banners: ['categories', 'dictionary', 'papers'],
    topics: ['papers'], resourceRequests: ['papers'], supportCenter: ['papers'],
    orders: ['payment'], reconciliations: ['payment'], membershipCards: ['payment'],
  }
  return !canAdmin(owner) && scopes[adminRoute.tab]?.includes(kind)
    ? `/api/v1/admin/options/${adminRoute.tab}/${kind}` : fallback
}
