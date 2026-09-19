import 'fake-indexeddb/auto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'
import { useExamStore } from '../stores/exam'

// 让草稿会话初始化失败（历史上等价于「非安全上下文下 crypto.randomUUID 不存在」）
vi.mock('../persistence', async importOriginal => ({
  ...await importOriginal<typeof import('../persistence')>(),
  draftSession: vi.fn(() => { throw new Error('crypto.randomUUID is not a function') }),
}))

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  fetchAvailable: vi.fn().mockResolvedValue({ 小学三年级: ['语文', '数学'] }),
  fetchScope: vi.fn().mockResolvedValue({ allowed: [] }),
  fetchTemplates: vi.fn().mockResolvedValue([]),
  upsertTemplate: vi.fn().mockResolvedValue(1),
  deleteTemplateOnServer: vi.fn().mockResolvedValue(undefined),
  fetchGenerationUsage: vi.fn().mockResolvedValue(null),
}))

const stores: ReturnType<typeof useExamStore>[] = []

afterEach(() => {
  for (const store of stores) { store.disposePersistence(); store.$dispose() }
  stores.length = 0
})

describe('草稿层故障不能连坐整个工作台', () => {
  it('draftSession 抛错时 init() 仍加载年级科目，并留下可用的草稿 runtime', async () => {
    setActivePinia(createPinia())
    useAuthStore().user = { id: 7, username: 'teacher', role: 'user' }
    const store = useExamStore()
    stores.push(store)

    await expect(store.init()).resolves.not.toThrow()

    // 工作台不能是空白：年级科目照常拉到
    expect(store.availableLoading).toBe(false)
    expect(store.available).toEqual({ 小学三年级: ['语文', '数学'] })
    expect(store.availableError).toBe('')
    // 降级要如实记录下来，且不能卡在 'loading'（界面上就是永远「正在恢复草稿」）
    expect(store.storageError).toContain('crypto.randomUUID')
    expect(store.draftState).not.toBe('loading')
    // 关键：runtime 仍然注册了，flushDraft 不再恒为 false（退不出登录就是被它拦的）
    expect(await store.flushDraft()).toBe(true)
  })
})
