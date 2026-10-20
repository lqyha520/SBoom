/** Login and inbox targets are rebuilt from a strict public-route allowlist. */
const routes: Record<string, readonly string[]> = {
  home: [], library: ['q', 'grade', 'subject', 'category', 'topic'], favorites: [], account: [], downloads: [], recent: [],
  paper: ['id'], topic: ['id'], messages: [], membership: ['contact'], orders: ['id'], closure: [],
  requests: ['id', 'title', 'grade', 'subject'], support: ['id', 'kind', 'paper'], privacy: ['kind'],
}
const servicePages = new Set(["membership", "support", "orders", "privacy", "requests", "messages", "closure"])
const ids = new Set(['id', 'paper', 'category', 'topic'])
const escaped = /%[0-9A-Fa-f]{2}/
export const HOME = '/pages/home/index'
/** 小程序 onLoad 的路径参数不做 URL 解码（H5 会自动解码），统一按"可能未解码"处理一次。 */
export function decodeParam(value: unknown): string {
  const raw = typeof value === 'string' ? value : ''
  if (!escaped.test(raw)) return raw
  try {
    const decoded = decodeURIComponent(raw)
    return /[\u0000-\u001f]/.test(decoded) ? raw : decoded
  } catch { return raw }
}
export function safeDestination(input: unknown): string {
  if (typeof input !== 'string' || input.length > 1400 || /[\\\r\n#]/.test(input)) return HOME
  // 平台差异：小程序原样带未解码的参数，H5 已解码。只有不像页面路径时才尝试解一次，解码结果仍走完整校验。
  const target = (input.startsWith('/pages/') || input.startsWith('/subpages/')) ? input : decodeParam(input)
  const match = /^\/(?:pages|subpages)\/([a-z]+)\/index(?:\?([^#]*))?$/.exec(target)
  if (!match || !routes[match[1]!]) return HOME
  const values = new Map<string, string>()
  try {
    for (const pair of (match[2] || '').split('&').filter(Boolean)) {
      const split = pair.indexOf('=')
      if (split < 1) return HOME
      const key = decodeURIComponent(pair.slice(0, split)), value = decodeURIComponent(pair.slice(split + 1))
      if (!routes[match[1]!]!.includes(key) || values.has(key) || /[\u0000-\u001f]/.test(value)) return HOME
      if (ids.has(key) && !/^[a-zA-Z0-9_-]{1,64}$/.test(value)) return HOME
      if (value.length > 120) return HOME
      if (key === 'contact' && value !== '1') return HOME
      if (key === 'kind' && !(match[1] === 'privacy' ? ['privacy', 'agreement'] : ['correction', 'download', 'membership', 'other']).includes(value)) return HOME
      values.set(key, value)
    }
  } catch { return HOME }
  if (['paper', 'topic'].includes(match[1]!) && !values.has('id')) return HOME
  const query = [...values].map(([key, value]) => key + '=' + encodeURIComponent(value)).join('&')
  return (servicePages.has(match[1]!) ? '/subpages/' : '/pages/') + match[1] + '/index' + (query ? '?' + query : '')
}
export function routeFromPage(page: { route?: string; options?: Record<string, unknown>; $page?: { options?: Record<string, unknown> } } | undefined) {
  if (!page?.route) return HOME
  const options = page.options || page.$page?.options || {}
  const key = page.route.split('/')[1] || ''
  // page.options 是平台原样给的路径参数（小程序不解码），所以先归一化再重新编码。
  const query = (routes[key] || []).filter(name => typeof options[name] === 'string').map(name => name + '=' + encodeURIComponent(decodeParam(options[name]))).join('&')
  return safeDestination('/' + page.route + (query ? '?' + query : ''))
}
export function loginUrl(target: string) { return '/pages/login/index?returnTo=' + encodeURIComponent(safeDestination(target)) }
export function shareCard(kind: 'home' | 'paper' | 'topic', id = '', title = '') {
  // Omitting imageUrl lets WeChat capture the current page.
  return { title: title.trim().slice(0, 100) || '习题库 · 每天一点进步', path: safeDestination('/pages/' + kind + '/index' + (id ? '?id=' + encodeURIComponent(id) : '')) }
}

/** Share the public paper chosen by a native button, never the private list. */
export function catalogShare(event: { target?: { dataset?: Record<string, unknown> } }, fallback = shareCard('home')) {
  const data = event.target?.dataset
  if (typeof data?.paperId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(data.paperId)) return fallback
  return shareCard('paper', data.paperId, typeof data.paperTitle === 'string' ? data.paperTitle : '')
}

/** 朋友圈分享：onShareTimeline 只能分享「当前页面路径」，因此仅返回 title + query。 */
export function shareTimeline(card = shareCard('home')) {
  return { title: card.title, query: card.path.split('?')[1] || '' }
}
