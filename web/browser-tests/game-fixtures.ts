import type { BrowserContext } from '@playwright/test'
import type { ApiSchemas } from '../../shared/api-schema'

/** 老游戏回归也使用真实的登录身份与云存档契约，不依赖本地预览服务器的后端。 */
export async function mockGameCloud(context: BrowserContext, owner?: number) {
  const saves = new Map<string, ApiSchemas['GameSave']>()
  if (owner) await context.route('**/api/v1/auth/me', route => route.fulfill({ json: { id: owner, username: 'teacher', role: 'user' } }))
  await context.route('**/api/v1/me/games**', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: [...saves.values()] } })
    const body = route.request().postDataJSON() as ApiSchemas['GameSaveInput']
    const id = new URL(route.request().url()).pathname.split('/').pop()! as ApiSchemas['GameSave']['game_id']
    const current = saves.get(id)
    if (body.revision !== (current?.revision || 0)) return route.fulfill({ status: 409, json: { detail: { error: '存档已更新', code: 'game_progress_conflict' } } })
    const value = { ...body, game_id: id, revision: body.revision + 1, updated_at: Math.floor(Date.now() / 1000) }
    saves.set(id, value)
    return route.fulfill({ json: value })
  })
}
