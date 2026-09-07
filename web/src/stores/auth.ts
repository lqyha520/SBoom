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
async function migrateLegacyData(uid: number) {
  const flag = `${userPrefix(uid)}migrated`
  if (localStorage.getItem(flag)) return
  const P = userPrefix(uid)

  // 1) 拷贝旧键到用户命名空间
  for (const k of LEGACY_KEYS) {
    if (localStorage.getItem(P + k)) continue // 已有该用户数据，不覆盖
    const v = localStorage.getItem(k)
    if (v != null) localStorage.setItem(P + k, v)
  }

  // 2) 模型配置已收归后台（/admin）：清除本地遗留的明文密钥
  localStorage.removeItem('lc_llm_cfg')
  localStorage.removeItem(P + 'lc_llm_cfg')

  // 3) 模板上传服务端，并与服务端列表合并（服务端优先）
  try {
    const localTpls = JSON.parse(localStorage.getItem(P + LS.myTemplates) || '[]')
    const serverTpls = await api.fetchTemplates()
    if (localTpls.length && !serverTpls.length) {
      await api.bulkUploadTemplates(localTpls)
    } else if (serverTpls.length) {
      // 服务端有数据（其他设备同步过）：服务端优先，补充本地独有的
      const names = new Set(serverTpls.map(t => t.name))
      const merged = [...serverTpls, ...localTpls.filter((t: any) => t && t.name && !names.has(t.name))]
      localStorage.setItem(P + LS.myTemplates, JSON.stringify(merged))
    }
  } catch { /* 忽略 */ }

  localStorage.setItem(flag, '1')
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as { id: number; username: string; role: string } | null,
    ready: false,
  }),
  actions: {
    /** 应用启动时调用（main.ts 在 mount 之前 await），确保 exam store 能拿到 lc_uid */
    async init() {
      try {
        const u = await api.fetchMe()
        if (u) {
          this.user = u
          localStorage.setItem(UID_KEY, String(u.id))
          await migrateLegacyData(u.id)
        } else {
          localStorage.removeItem(UID_KEY)
        }
      } catch {
        // 后端不可达：保持未登录，让登录页展示错误
        localStorage.removeItem(UID_KEY)
      } finally {
        this.ready = true
      }
    },

    async login(username: string, password: string) {
      const u = await api.login(username, password)
      this.user = u
      localStorage.setItem(UID_KEY, String(u.id))
      await migrateLegacyData(u.id)
      location.reload() // 整页刷新，让所有 store 按新用户命名空间重新初始化
    },

    async register(username: string, password: string) {
      const u = await api.register(username, password)
      this.user = u
      localStorage.setItem(UID_KEY, String(u.id))
      location.reload()
    },

    async logout() {
      try {
        await api.logout()
      } catch { /* 即使后端失败也继续本地登出 */ }
      this.user = null
      localStorage.removeItem(UID_KEY)
      location.reload()
    },
  },
})
