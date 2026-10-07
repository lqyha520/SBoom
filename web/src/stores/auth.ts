import { defineStore } from 'pinia'
import * as api from '../api'
import { LS } from '../constants'

/** 当前登录用户在 localStorage 中的命名空间标识（exam store 依赖它做数据隔离） */
export const UID_KEY = 'lc_uid'

const LEGACY_KEYS = [
  LS.customTypes,
  LS.template,
  LS.customTemplate,
  LS.paperStyle,
  LS.myTemplates,
]

export function userPrefix(uid: string | number): string {
  return `lc_u${uid}_`
}

/**
 * 单用户 → 多用户的一次性本地数据迁移：
 * 1. 把旧的全局 lc_* 数据拷贝到 lc_u{uid}_* 命名空间（仅当该用户命名空间还是空的）
 * 2. 清除本地遗留的 LLM 明文密钥（模型配置已收归后台统一管理）
 * 3. 「我的模板」批量上传到服务端（跨设备同步）
 */
function rememberUser(uid: number | null) {
  api.bindWorkspaceOwner(uid == null ? '' : String(uid))
  try {
    if (uid == null) localStorage.removeItem(UID_KEY)
    else localStorage.setItem(UID_KEY, String(uid))
  } catch { /* Storage restrictions must not turn a valid session into a login failure. */ }
}

async function migrateLegacyData(uid: number) {
  try {
    const prefix = userPrefix(uid)
    const flag = prefix + 'migrated'
    const priorOwner = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
      .find(key => /^lc_u\d+_migrated$/.test(key || ''))?.match(/^lc_u(\d+)_/)?.[1]
    const owner = localStorage.getItem('lc_legacy_owner') || priorOwner || String(uid)
    localStorage.setItem('lc_legacy_owner', owner)
    if (localStorage.getItem(flag)) return
    if (owner === String(uid)) {
      for (const key of LEGACY_KEYS) {
        if (localStorage.getItem(prefix + key)) continue
        const value = localStorage.getItem(key)
        if (value != null) localStorage.setItem(prefix + key, value)
      }
    }
    localStorage.removeItem('lc_llm_cfg')
    localStorage.removeItem(prefix + 'lc_llm_cfg')
    const localTemplates = JSON.parse(localStorage.getItem(prefix + LS.myTemplates) || '[]')
    if (Array.isArray(localTemplates) && localTemplates.length) {
      try { await api.bulkUploadTemplates(localTemplates) }
      catch { /* The exam store keeps unsynchronized local templates pending. */ }
    }
    localStorage.setItem(flag, '1')
  } catch { /* A disabled localStorage does not prevent using the account. */ }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as { id: number; username: string; role: string } | null,
    ready: false,
    bootError: '',
  }),
  actions: {
    /** 网络错误保留账号标识；只有明确的无会话响应才广播退出。 */
    async init() {
      this.ready = false
      this.bootError = ''
      try {
        const u = await api.fetchMe()
        if (u) {
          this.user = u
          rememberUser(u.id)
          await migrateLegacyData(u.id)
        } else {
          this.user = null
          rememberUser(null)
        }
      } catch (error) {
        this.bootError = error instanceof Error ? error.message : '无法连接服务，请稍后重试'
      } finally {
        this.ready = true
      }
    },

    async login(username: string, password: string) {
      const u = await api.login(username, password)
      try { localStorage.removeItem('lc_purge:' + u.id) } catch { /* 存储限制不应阻止登录。 */ }
      this.user = u
      rememberUser(u.id)
      await migrateLegacyData(u.id)
      location.reload() // 整页刷新，让所有 store 按新用户命名空间重新初始化
    },

    async register(username: string, password: string) {
      const u = await api.register(username, password)
      this.user = u
      rememberUser(u.id)
      location.reload()
    },

    async logout(clearLocal = false) {
      await api.logout()
      if (clearLocal && this.user) {
        const { clearAccountData } = await import('../local-storage')
        await clearAccountData(String(this.user.id))
      }
      this.user = null
      rememberUser(null)
      location.reload()
    },
  },
})
