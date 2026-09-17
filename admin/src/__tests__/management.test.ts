import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import CatalogBatchDialog from '../components/CatalogBatchDialog.vue'
import DictionaryManager from '../components/DictionaryManager.vue'
import UsersPage from '../components/UsersPage.vue'
import AdminAccounts from '../components/AdminAccounts.vue'
import type { CatalogPaper } from '../catalog'
import { uiStubs } from './ui-stubs'

const mocks = vi.hoisted(() => ({ request: vi.fn(), batch: vi.fn(), tags: vi.fn() }))
vi.mock('../api', async importOriginal => ({ ...await importOriginal<typeof import('../api')>(), request: mocks.request }))
vi.mock('../experience', () => ({ batchCatalog: mocks.batch }))
vi.mock('../growth', async importOriginal => ({ ...await importOriginal<typeof import('../growth')>(), getTags: mocks.tags }))

const user = { id: 1, username: 'admin', role: 'admin' }
let wrapper: VueWrapper
function button(label: string) {
  return wrapper.findAll('button').find(item => item.text() === label)!
}
function batch() {
  wrapper = mount(CatalogBatchDialog, {
    props: { open: true, adminId: 1, items: [{ id: 'paper', revision: 3 } as CatalogPaper], categories: [{ value: 'cat', label: '分类' }] },
    global: { stubs: uiStubs },
  })
}
beforeEach(() => {
  mocks.request.mockReset(); mocks.batch.mockReset(); mocks.tags.mockReset()
  mocks.batch.mockResolvedValue({ updated: 1 })
  mocks.tags.mockResolvedValue({ items: [
    { id: 'k1', kind: 'knowledge', name: '加法', is_visible: true },
    { id: 'k2', kind: 'knowledge', name: '减法', is_visible: true },
  ] })
})
afterEach(() => wrapper?.unmount())

describe('批量资料管理', () => {
  it('勾选、取消知识点后提交剩余选项', async () => {
    batch()
    await wrapper.get('select[aria-label="批量操作类型"]').setValue('tags')
    await flushPromises()
    const choices = wrapper.findAll('input[type="checkbox"]')
    await choices[0]!.setValue(true)
    await choices[1]!.setValue(true)
    await choices[0]!.setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.batch).toHaveBeenCalledWith(1, expect.any(Array), expect.objectContaining({ action: 'tags', tag_ids: ['k2'] }))
    expect(wrapper.emitted('saved')).toEqual([[1]])
  })
  it('未确认发布不能提交，确认后才发送发布请求', async () => {
    batch()
    await wrapper.get('select').setValue('published')
    expect(button('应用到所选资料').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(mocks.batch).not.toHaveBeenCalled()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.batch).toHaveBeenCalledWith(1, expect.any(Array), expect.objectContaining({ action: 'published', confirm_publication: true }))
  })
  it('冲突时保留弹窗并展示服务端错误', async () => {
    batch()
    mocks.batch.mockRejectedValueOnce(new Error('资料已被其他管理员修改'))
    await wrapper.findAll('select')[1]!.setValue('cat')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('资料已被其他管理员修改')
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})

describe('知识点字典', () => {
  function dictionary(linked = true) {
    mocks.request.mockImplementation(async (url: string) => {
      if (url.endsWith('/unlisted')) return { grade: [], subject: [] }
      if (url.endsWith('/links')) return { links: linked ? [{ parent_id: 'g1', child_id: 's1' }] : [] }
      return { items: [
        { id: 'g1', kind: 'grade', value: '小学一年级', parent: '', is_visible: true },
        { id: 's1', kind: 'subject', value: '数学', parent: '', is_visible: true },
      ] }
    })
    wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(DictionaryManager, { user })) }), { global: { stubs: uiStubs } })
  }
  it('从字典表单新增知识点时携带年级和科目', async () => {
    dictionary(); await flushPromises()
    await button('知识点').trigger('click')
    await button('新建知识点').trigger('click')
    await wrapper.get('#dict-form input').setValue('十以内加法')
    await wrapper.get('#dict-form').trigger('submit')
    await flushPromises()
    const call = mocks.request.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(call[1].body)).toMatchObject({ kind: 'knowledge_point', parent: 'g1|s1', value: '十以内加法' })
    expect(wrapper.text()).toContain('知识点字典已更新')
  })
  it('没有关联科目时不允许创建孤立知识点', async () => {
    dictionary(false); await flushPromises()
    await button('知识点').trigger('click')
    expect(button('新建知识点')).toBeUndefined()
    expect(wrapper.text()).toContain('先选择年级和科目')
  })
})

describe.each([[UsersPage, 'user'], [AdminAccounts, 'admin']] as const)('服务端分页 %s', (component, role) => {
  it('翻页请求下一页，搜索重置偏移且使用服务端总数', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ users: [], total: 43, limit: 20, offset: 0 })))
    vi.stubGlobal('fetch', fetchMock)
    try {
      wrapper = mount(component, { props: { user }, global: { stubs: uiStubs } })
      await flushPromises()
      expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`role=${role}&limit=20&offset=0`)
      expect(wrapper.text()).toContain('43')
      await button('下一页').trigger('click'); await flushPromises()
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('offset=20')
      await wrapper.get('form.table-search input').setValue('张老师')
      await wrapper.get('form.table-search').trigger('submit'); await flushPromises()
      const url = new URL(String(fetchMock.mock.calls.at(-1)?.[0]), 'http://localhost')
      expect(url.searchParams.get('offset')).toBe('0')
      expect(url.searchParams.get('query')).toBe('张老师')
    } finally { vi.unstubAllGlobals() }
  })
})
