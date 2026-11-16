import type { RequestScope } from './latest-request'

/** 首次来源用于注册归属；当前扫码的落地内容与其分别保存。 */
const KEY = 'lc_referral_entry', VISITS_KEY = 'lc_referral_visits'
const MAX_AGE = 7 * 86400 * 1000
const pattern = /^[au]_[0-9a-f]{20}$/
interface Entry { code: string; at: number; entryKey?: string; visitId?: string }
type EntryResult = { visit_id: string; destination: string; tracked: boolean }
type Transport = { enter: (code: string, key: string) => Promise<EntryResult>; start: (id: string) => Promise<unknown> }
let pending: Entry | null = null, visits: Entry[] | null = null
let ownCode = '', signedIn = false
let transport: Transport | null = null
const flights = new Map<string, Promise<EntryResult | null>>()
let flight: Promise<unknown> | null = null, landing = '', landingCode = '', generation = 0
let landingCancelled = false
const entryKey = () => Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2)
export function configureReferralTracking(value: Transport | null) { transport = value }
function valid(value: unknown): value is string { return typeof value === 'string' && pattern.test(value) }
function entryFrom(value: unknown): Entry | null {
  if (!value || typeof value !== 'object') return null
  const saved = value as Entry
  if (!valid(saved.code) || !Number.isFinite(saved.at) || Date.now() - saved.at > MAX_AGE || saved.at > Date.now()) return null
  return { code: saved.code, at: saved.at,
    ...(/^[a-zA-Z0-9_-]{16,64}$/.test(saved.entryKey || '') ? { entryKey: saved.entryKey } : {}),
    ...(/^[0-9a-f]{32}$/.test(saved.visitId || '') ? { visitId: saved.visitId } : {}) }
}
function persist() {
  try {
    if (pending) uni.setStorageSync(KEY, pending)
    if (visits) uni.setStorageSync(VISITS_KEY, visits)
  } catch { /* 存储不可用时仍可在当前会话跟踪。 */ }
}
function read() {
  if (!pending) { try { pending = entryFrom(uni.getStorageSync(KEY)) } catch { /* 保留内存状态。 */ } }
  if (pending && !entryFrom(pending)) clearPending()
  return pending?.code || ''
}
function clearPending() {
  pending = null
  try { uni.removeStorageSync(KEY) } catch { /* 内存状态仍已清除。 */ }
}
function visit(code: string): Entry {
  if (!visits) {
    try {
      const saved = uni.getStorageSync(VISITS_KEY)
      visits = Array.isArray(saved) ? saved.map(entryFrom).filter((item): item is Entry => !!item) : []
    } catch { visits = [] }
  }
  visits = visits.filter(item => !!entryFrom(item))
  let entry = visits.find(item => item.code === code)
  if (!entry) {
    entry = pending?.code === code ? pending : { code, at: Date.now() }
    visits = [...visits.slice(-49), entry]
  }
  entry.entryKey ||= entryKey()
  if (pending?.code === code) { pending.entryKey = entry.entryKey; pending.visitId = entry.visitId }
  persist()
  return entry
}
function track(code: string) {
  if (!transport) return Promise.resolve(null)
  const entry = visit(code)
  const running = flights.get(entry.entryKey!)
  if (running) return running
  const request = transport.enter(code, entry.entryKey!).then(result => {
    if (/^[0-9a-f]{32}$/.test(result.visit_id)) {
      entry.visitId = result.visit_id
      if (pending && pending.entryKey === entry.entryKey) pending.visitId = result.visit_id
      persist()
    }
    return result
  }).catch(() => null).finally(() => { flights.delete(entry.entryKey!) })
  flights.set(entry.entryKey!, request)
  return request
}
export function cancelReferralLanding() { landingCancelled = true; landing = '' }
export async function takeReferralLanding(options: { scope?: RequestScope; timeoutMs?: number } = {}) {
  const current = generation
  let timer: ReturnType<typeof setTimeout> | undefined, unregister = () => {}
  try {
    await Promise.race([flight, new Promise<void>(resolve => {
      const cancel = () => { if (current === generation) cancelReferralLanding(); resolve() }
      unregister = options.scope?.onCancel(cancel) || unregister
      timer = setTimeout(cancel, options.timeoutMs ?? 1500)
    })])
    if (current !== generation || landingCancelled) return ''
    const result = landing; landing = ''; return result
  } finally { clearTimeout(timer); unregister() }
}
export async function beginReferralRegistration() {
  const code = read()
  if (code && !pending?.visitId) {
    // 弱网时不让统计请求拖住注册。
    let timer: ReturnType<typeof setTimeout> | undefined
    try { await Promise.race([track(code), new Promise(resolve => { timer = setTimeout(resolve, 1500) })]) }
    finally { clearTimeout(timer) }
  }
  if (pending?.visitId && transport) void transport.start(pending.visitId).catch(() => {})
}
export function captureReferral(options?: { path?: string; query?: Record<string, unknown> }) {
  const existing = read(), query = options?.query || {}
  let scene = query.scene
  if (typeof scene === 'string') { try { scene = decodeURIComponent(scene) } catch { scene = '' } }
  const code = valid(query.ref) ? query.ref : valid(scene) ? scene : ''
  if (!code) return
  if (!signedIn && !existing) { pending = { code, at: Date.now() }; persist() }
  if (landingCode === code) return
  landingCode = code; landing = ''; landingCancelled = false
  const current = ++generation
  flight = track(code).then(result => {
    if (current !== generation) return
    if (!result) { landingCode = ''; return }
    // 分享资料详情时尊重原页面，只有首页入口消费活动落地内容。
    if (!landingCancelled && (!options?.path || options.path === 'pages/home/index') && /^\/pages\/(paper|topic)\/index\?id=[a-zA-Z0-9_-]+$/.test(result.destination)) landing = result.destination
  }).finally(() => { if (current === generation) flight = null })
}
export function referralPayload(): { referral_code?: string; referral_visit_id?: string } { const value = read(); return value ? { referral_code: value, ...(pending?.visitId ? { referral_visit_id: pending.visitId } : {}) } : {} }
export function bindReferralUser(user: { referral_code?: string } | null, preserveEntry = false, preserveLanding = false) {
  signedIn = !!user
  ownCode = valid(user?.referral_code) ? user.referral_code : ''
  if (!preserveEntry) clearPending()
  if (!preserveEntry && !preserveLanding) { generation++; flight = null; landingCode = ''; landing = '' }
}
export function referralSharePath(path: string) {
  const code = ownCode || (!signedIn ? read() : '')
  return code ? path + (path.includes('?') ? '&' : '?') + 'ref=' + code : path
}
