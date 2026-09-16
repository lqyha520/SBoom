/** Login and inbox targets are rebuilt from a strict public-route allowlist. */
const routes: Record<string, readonly string[]> = {
  home: [], library: ['q', 'grade', 'subject', 'category', 'topic'], favorites: [], account: [], downloads: [], recent: [],
  paper: ['id'], topic: ['id'], messages: [], membership: [], orders: ['id'], closure: [],
  requests: ['id', 'title', 'grade', 'subject'], support: ['id', 'kind', 'paper'], privacy: ['kind'],
}
const ids = new Set(['id', 'paper', 'category', 'topic'])
export const HOME = '/pages/home/index'
export function safeDestination(input: unknown): string {
  if (typeof input !== 'string' || input.length > 1400 || /[\\\r\n#]/.test(input)) return HOME
  const match = /^\/pages\/([a-z]+)\/index(?:\?([^#]*))?$/.exec(input)
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
      if (key === 'kind' && !(match[1] === 'privacy' ? ['privacy', 'agreement'] : ['correction', 'download', 'membership', 'other']).includes(value)) return HOME
      values.set(key, value)
    }
  } catch { return HOME }
  if (['paper', 'topic'].includes(match[1]!) && !values.has('id')) return HOME
  const query = [...values].map(([key, value]) => key + '=' + encodeURIComponent(value)).join('&')
  return '/pages/' + match[1] + '/index' + (query ? '?' + query : '')
}
export function routeFromPage(page: { route?: string; options?: Record<string, unknown>; $page?: { options?: Record<string, unknown> } } | undefined) {
  if (!page?.route) return HOME
  const options = page.options || page.$page?.options || {}
  const key = page.route.split('/')[1] || ''
  const query = (routes[key] || []).filter(name => typeof options[name] === 'string').map(name => name + '=' + encodeURIComponent(String(options[name]))).join('&')
  return safeDestination('/' + page.route + (query ? '?' + query : ''))
}
export function loginUrl(target: string) { return '/pages/login/index?returnTo=' + encodeURIComponent(safeDestination(target)) }
export function shareCard(kind: 'home' | 'paper' | 'topic', id = '', title = '') {
  return { title: title.trim().slice(0, 100) || '习题库 · 每天一点进步', path: safeDestination('/pages/' + kind + '/index' + (id ? '?id=' + encodeURIComponent(id) : '')), imageUrl: '/static/banners/study.jpg' }
}
