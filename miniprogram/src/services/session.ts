import { reactive } from 'vue'
import type { Authenticated, User } from '../types'
import { authGeneration, configureSession, errorMessage, patchPassword, patchProfile, request, TOKEN_KEY, unauthorizedHandler } from './api'
import { clearAssetCache } from './assets'

export const session = reactive({ user: null as User | null, ready: false, error: '' })
let initializing: Promise<boolean> | null = null

export function clearSession() {
  configureSession('')
  session.user = null
  session.ready = true
  clearAssetCache()
  try { uni.removeStorageSync(TOKEN_KEY) } catch { /* A revoked server session remains invalid without local storage. */ }
}
unauthorizedHandler(clearSession)

export function acceptSession(user: User, token = '') {
  clearAssetCache()
  configureSession(token, String(user.id))
  session.user = user
  session.ready = true
  session.error = ''
  if (token) {
    try { uni.setStorageSync(TOKEN_KEY, token) } catch { /* The current session can still run in memory. */ }
  }
}

export function ensureSession(): Promise<boolean> {
  if (session.ready) return Promise.resolve(!!session.user)
  if (initializing) return initializing
  initializing = (async () => {
    let epoch = authGeneration()
    try {
      let token = ''
      token = String(uni.getStorageSync(TOKEN_KEY) || '')
      if (!token) { session.ready = true; return false }
      configureSession(token)
      epoch = authGeneration()
      const user = await request<User>('/api/v1/mini/me')
      acceptSession(user, token)
      return true
    } catch (error) {
      if (epoch === authGeneration()) { session.error = errorMessage(error); clearSession() }
      return !!session.user
    } finally { initializing = null }
  })()
  return initializing
}

export async function loginWeb(username: string, password: string) {
  const result = await request<Authenticated>('/api/v1/mini/login-password', 'POST', { username, password })
  loginMini(result)
}

export async function registerWeb(username: string, password: string) {
  const result = await request<Authenticated>('/api/v1/mini/register', 'POST', { username, password })
  loginMini(result)
}

export function loginMini(result: Authenticated) { acceptSession(result.user, result.token) }

export async function refreshMembership() {
  const user = await request<User>('/api/v1/mini/me')
  if (session.user?.is_vip && !user.is_vip) clearAssetCache()
  session.user = user
}

/** 保存改资料结果：接口回的就是最新的自己，直接同步，不必再拉一次 /me。 */
export async function saveProfile(payload: { username?: string; avatar?: string }) {
  const user = await patchProfile(payload)
  session.user = user
  return user
}

export async function savePassword(current: string, next: string) {
  const user = await patchPassword(current, next)
  session.user = user
  return user
}

export async function logout() {
  await request<void>('/api/v1/mini/logout', 'POST')
  clearSession()
}
