import { navigatePage } from './page-navigation'
import { reactive } from 'vue'
import type { Authenticated, User } from '../types'
import { authGeneration, configureSession, errorMessage, patchPassword, patchProfile, request, TOKEN_KEY, unauthorizedHandler, type ReadOptions } from './api'
import { clearAssetCache } from './assets'
import { recordEvent } from './experience'
import { inboxState } from './growth'
import { loginUrl, routeFromPage } from './return-route'

export const session = reactive({ user: null as User | null, ready: false, error: '' })

/** Public pages ask for login only when an action needs the user's account. */
export function requireLogin(target?: string): boolean {
  if (session.user) return true
  const pages = getCurrentPages()
  navigatePage({ url: loginUrl(target || routeFromPage(pages[pages.length - 1])) })
  return false
}
let initializing: Promise<boolean> | null = null
let activeKey = ''
function markActive() {
  if (!session.user) return
  const key = session.user.id + ':' + Math.floor((Date.now() / 1000 + 28800) / 86400)
  if (activeKey === key) return
  activeKey = key
  void recordEvent('active').catch(() => { if (activeKey === key) activeKey = '' })
}

export function clearSession() {
  inboxState.unread = 0; inboxState.pending = 0
  configureSession('')
  session.user = null
  session.ready = true
  session.error = ''
  clearAssetCache()
  try { uni.removeStorageSync(TOKEN_KEY) } catch { /* A revoked server session remains invalid without local storage. */ }
}
unauthorizedHandler(clearSession)

export function acceptSession(user: User, token = '') {
  if (configureSession(token, String(user.id))) {
    inboxState.unread = 0; inboxState.pending = 0
    clearAssetCache()
  }
  session.user = user
  session.ready = true
  session.error = ''
  markActive()
  if (token) {
    try { uni.setStorageSync(TOKEN_KEY, token) } catch { /* The current session can still run in memory. */ }
  }
}

export function ensureSession(): Promise<boolean> {
  if (session.ready && !session.error) { markActive(); return Promise.resolve(!!session.user) }
  if (initializing) return initializing
  initializing = Promise.resolve().then(async () => {
    let epoch = authGeneration()
    try {
      let token = ''
      token = String(uni.getStorageSync(TOKEN_KEY) || '')
      if (!token) { session.ready = true; return false }
      configureSession(token)
      epoch = authGeneration()
      const user = await request<User>('/api/v1/mini/me')
      if (epoch !== authGeneration()) return !!session.user
      acceptSession(user, token)
      return true
    } catch (error) {
      // Explicit authorization failures are handled by the API's unauthorized handler.
      // A timeout or temporary server failure must leave the saved token available for retry.
      if (epoch === authGeneration()) { session.error = errorMessage(error); session.ready = true }
      return !!session.user
    }
  }).finally(() => { initializing = null })
  return initializing
}

export function loginMini(result: Authenticated) { acceptSession(result.user, result.token) }

export async function refreshMembership(options: ReadOptions = {}) {
  const previous = session.user
  const user = await request<User>('/api/v1/mini/me', 'GET', undefined, options)
  // A refresh started before saving a photo must not overwrite the new profile.
  if (session.user !== previous) return
  if (session.user?.is_vip && !user.is_vip) clearAssetCache()
  session.user = user
}

/** 保存改资料结果：接口回的就是最新的自己，直接同步，不必再拉一次 /me。 */
export async function saveProfile(payload: { nickname?: string; avatar?: string }) {
  const user = await patchProfile(payload)
  session.user = user
  return user
}

export async function saveAvatar(payload: { image: string; nickname?: string }) {
  const user = await request<User>('/api/v1/mini/me/avatar', 'POST', payload)
  session.user = user
  return user
}

export async function savePassword(current: string, next: string) {
  const user = await patchPassword(current, next)
  session.user = user
  return user
}

export async function logout() {
  const revoke = request<void>('/api/v1/mini/logout', 'POST')
  clearSession()
  void revoke.catch(() => {})
}
