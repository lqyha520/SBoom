import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { adminRoute } from '../navigation'
import { newDraft, newMaterial, type DraftData, type MaterialData } from '../xhs-workflow'
import XhsDrafts from '../components/XhsDrafts.vue'
import XhsMaterials from '../components/XhsMaterials.vue'

const mocks = vi.hoisted(() => ({ request: vi.fn() }))
const sourceMaterial = () => ({ ...newMaterial(), title: '资料', questions: [{ stem: '1+1=?', options: [], answer: '2', analysis: '一加一等于二', quality_issues: [] }] })
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: mocks.request }))
let wrapper: VueWrapper
beforeEach(() => { localStorage.clear(); mocks.request.mockReset(); window.confirm = vi.fn(() => false) })
afterEach(() => { wrapper?.unmount(); localStorage.clear() })

it.each(['copy', 'material'] as const)('生成 %s 期间保存的修改不被自动覆盖，确认后才能应用保留结果', async kind => {
  const copy = kind === 'copy'
  Object.assign(adminRoute, { tab: copy ? 'xhsDrafts' : 'xhsMaterials', query: 'id=record-one' })
  let data: DraftData | MaterialData = copy ? { ...newDraft(), title: '笔记', body: '原正文' } : { ...newMaterial(), title: '资料', keyword: '口算' }
  let saved = { id: 'record-one', kind: copy ? 'drafts' : 'materials', parent_id: 'parent-one', title: data.title, status: 'draft', revision: 1, data, created_at: '', updated_at: '' }
  const parent = { id: 'parent-one', kind: copy ? 'materials' : 'ideas', parent_id: null, revision: 1, title: '资料', status: 'draft', data: sourceMaterial() }
  let complete!: (value: unknown) => void
  mocks.request.mockImplementation((path: string, options?: RequestInit) => {
    if (path === '/api/v1/scope/available') return Promise.resolve({ available: { '小学一年级': ['数学'] } })
    if (path === '/api/v1/generation/options?kind=text') return Promise.resolve({ timeout_ms: 300000, revision: 'config-one' })
    if (path === '/api/v1/admin/xhs-workflow/generate-copy' || path === '/api/v1/generate') return new Promise(resolve => { complete = resolve })
    if (options?.method === 'PUT') {
      const payload = JSON.parse(options.body as string)
      saved = { ...saved, revision: saved.revision + 1, data: payload.data }
      return Promise.resolve(JSON.parse(JSON.stringify(saved)))
    }
    return Promise.resolve(JSON.parse(JSON.stringify(path.endsWith('parent-one') ? parent : saved)))
  })
  wrapper = mount(copy ? XhsDrafts : XhsMaterials, { props: { user: { id: 7, username: 'tester', role: 'admin', is_super_admin: true } },
    global: { stubs: { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true } } })
  const vm = wrapper.vm as unknown as { w: { readRoute: () => Promise<void>; save: () => Promise<boolean> }; data: DraftData & MaterialData; generate: () => Promise<void>; applyGenerated: () => Promise<void> }
  await vm.w.readRoute()
  const running = vm.generate()
  await flushPromises()
  if (copy) { vm.data.body = '等待期间保存的新正文'; vm.data.audience = '老师' }
  else vm.data.keyword = '用户改为看图列式'
  expect(await vm.w.save()).toBe(true)
  const output = copy ? { draft: { ...newDraft(), title: '模型笔记', headline: '模型标题', body: '原输入生成的正文' }, request_id: 'request-one', material_id: 'parent-one', material_revision: 1 }
    : { questions: [{ stem: '1+1=?', answer: '2', analysis: '一加一等于二' }], request_id: 'request-one' }
  complete(output)
  await running
  data = saved.data
  expect(copy ? (data as DraftData).body : (data as MaterialData).questions.length).toBe(copy ? '等待期间保存的新正文' : 0)
  await flushPromises()
  expect(wrapper.find('details').exists()).toBe(true)
  await vm.applyGenerated()
  expect(copy ? (saved.data as DraftData).body : (saved.data as MaterialData).questions.length).toBe(copy ? '等待期间保存的新正文' : 0)
  vi.mocked(window.confirm).mockReturnValue(true)
  await vm.applyGenerated()
  expect(copy ? (saved.data as DraftData).body : (saved.data as MaterialData).questions.length).toBe(copy ? '原输入生成的正文' : 1)
  expect(copy ? (saved.data as DraftData).audience : (saved.data as MaterialData).keyword).toBe(copy ? '老师' : '用户改为看图列式')
})

it('版本未变化时仍能正常应用生成结果', async () => {
  Object.assign(adminRoute, { tab: 'xhsDrafts', query: 'id=record-one' })
  let saved = { id: 'record-one', kind: 'drafts', parent_id: 'parent-one', title: '笔记', status: 'draft', revision: 1,
    data: { ...newDraft(), title: '笔记', body: '原正文' }, created_at: '', updated_at: '' }
  mocks.request.mockImplementation(async (path: string, options?: RequestInit) => {
    if (path.includes('generation/options')) return { timeout_ms: 300000, revision: 'config-one' }
    if (path.endsWith('generate-copy')) return { draft: { ...newDraft(), headline: '模型标题', body: '新正文' }, request_id: 'normal-request', material_id: 'parent-one', material_revision: 1 }
    if (options?.method === 'PUT') { saved = { ...saved, revision: saved.revision + 1, data: JSON.parse(options.body as string).data } }
    return JSON.parse(JSON.stringify(path.endsWith('parent-one') ? { id: 'parent-one', revision: 1, data: sourceMaterial() } : saved))
  })
  wrapper = mount(XhsDrafts, { props: { user: { id: 7, username: 'tester', role: 'admin', is_super_admin: true } },
    global: { stubs: { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true } } })
  const vm = wrapper.vm as unknown as { w: { readRoute: () => Promise<void> }; generate: () => Promise<void> }
  await vm.w.readRoute(); await vm.generate()
  expect(saved.data.body).toBe('新正文')
  expect(window.confirm).not.toHaveBeenCalled()
})

it.each(['updated', 'unrelated'] as const)('资料来源 %s 时保留文案，核对后才允许应用正确来源的旧版本', async state => {
  Object.assign(adminRoute, { tab: 'xhsDrafts', query: 'id=record-one' })
  let saved = { id: 'record-one', kind: 'drafts', parent_id: 'parent-one', title: '笔记', status: 'draft', revision: 1,
    data: { ...newDraft(), title: '笔记', body: '用户原正文' }, created_at: '', updated_at: '' }
  let materialRevision = 1, complete!: (value: unknown) => void
  mocks.request.mockImplementation(async (path: string, options?: RequestInit) => {
    if (path.includes('generation/options')) return { timeout_ms: 300000, revision: 'config-one' }
    if (path.endsWith('generate-copy')) return new Promise(resolve => { complete = resolve })
    if (path.endsWith('parent-one')) return { id: 'parent-one', kind: 'materials', title: '资料', revision: materialRevision, data: sourceMaterial() }
    if (options?.method === 'PUT') saved = { ...saved, revision: saved.revision + 1, data: JSON.parse(options.body as string).data }
    return structuredClone(saved)
  })
  wrapper = mount(XhsDrafts, { props: { user: { id: 7, username: 'tester', role: 'admin', is_super_admin: true } },
    global: { stubs: { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true } } })
  const vm = wrapper.vm as unknown as { w: { readRoute: () => Promise<void> }; generate: () => Promise<void>; applyGenerated: () => Promise<void> }
  await vm.w.readRoute()
  const running = vm.generate(); await flushPromises()
  materialRevision = 2
  complete({ draft: { ...newDraft(), headline: '旧资料标题', body: '旧资料正文' }, request_id: 'source-request', material_id: state === 'updated' ? 'parent-one' : 'wrong-parent', material_revision: 1 })
  await running; await flushPromises()
  expect(saved.data.body).toBe('用户原正文')
  expect(wrapper.find('details').exists()).toBe(true)
  await vm.applyGenerated()
  expect(saved.data.body).toBe('用户原正文')
  vi.mocked(window.confirm).mockReturnValue(true)
  await vm.applyGenerated(); await flushPromises()
  expect(saved.data.body).toBe(state === 'updated' ? '旧资料正文' : '用户原正文')
  if (state === 'updated') {
    expect(saved.data.source_material_revision).toBe(1)
    expect(wrapper.text()).toContain('当前文案仍基于旧版本')
  } else expect(window.confirm).not.toHaveBeenCalled()
})

it.each([['material', 'edit'], ['material', 'switch'], ['copy', 'edit'], ['copy', 'switch']] as const)(
  '%s 生成前的读取期间发生 %s，不保存另一份输入或发起模型请求', async (kind, change) => {
    const copy = kind === 'copy', tab = copy ? 'xhsDrafts' : 'xhsMaterials'
    Object.assign(adminRoute, { tab, query: 'id=record-one' })
    const saved = { id: 'record-one', kind: copy ? 'drafts' : 'materials', parent_id: 'parent-one', title: '当前内容', status: 'draft', revision: 1,
      data: copy ? { ...newDraft(), title: '当前内容', body: '用户正文' } : { ...newMaterial(), title: '当前内容', keyword: '口算' }, created_at: '', updated_at: '' }
    const parent = { id: 'parent-one', kind: copy ? 'materials' : 'ideas', revision: 1, title: '资料', data: sourceMaterial() }
    let hold = false, complete!: (value: unknown) => void
    const mutations: string[] = []
    mocks.request.mockImplementation(async (path: string, options?: RequestInit) => {
      if (options?.method === 'PUT' || options?.method === 'POST') mutations.push(path)
      if (hold && (copy ? path.endsWith('parent-one') : path === '/api/v1/scope/available')) return new Promise(resolve => { complete = resolve })
      if (path === '/api/v1/scope/available') return { available: { '小学一年级': ['数学'] } }
      if (path.endsWith('parent-one')) return structuredClone(parent)
      if (path.endsWith('record-two')) return { ...structuredClone(saved), id: 'record-two', data: { ...saved.data, title: '另一份内容' } }
      return structuredClone(saved)
    })
    wrapper = mount(copy ? XhsDrafts : XhsMaterials, { props: { user: { id: 7, username: 'tester', role: 'admin', is_super_admin: true } },
      global: { stubs: { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true } } })
    const vm = wrapper.vm as unknown as { w: { readRoute: () => Promise<void> }; data: DraftData & MaterialData; generate: () => Promise<void> }
    await vm.w.readRoute(); hold = true
    const running = vm.generate(); await flushPromises(); hold = false
    if (change === 'switch') { Object.assign(adminRoute, { query: 'id=record-two' }); await flushPromises() }
    else if (copy) vm.data.body = '读取期间修改的正文'
    else vm.data.keyword = '读取期间修改的知识点'
    complete(copy ? parent : { available: { '小学一年级': ['数学'] } }); await running
    expect(mutations).toEqual([])
    if (change === 'switch') expect(vm.data.title).toBe('另一份内容')
    else expect(wrapper.text()).toContain('已修改，请重新点击生成')
  },
)

it('生成文案前自动读取最新关联资料，并把实际使用的版本保存到文案', async () => {
  Object.assign(adminRoute, { tab: 'xhsDrafts', query: 'id=record-one' })
  let materialRevision = 1
  let saved = { id: 'record-one', kind: 'drafts', parent_id: 'parent-one', title: '笔记', status: 'draft', revision: 1,
    data: { ...newDraft(), title: '笔记', body: '原正文' }, created_at: '', updated_at: '' }
  mocks.request.mockImplementation(async (path: string, options?: RequestInit) => {
    if (path.endsWith('parent-one')) return { id: 'parent-one', revision: materialRevision, data: sourceMaterial() }
    if (path.includes('generation/options')) return { timeout_ms: 300000, revision: 'config-one' }
    if (path.endsWith('generate-copy')) {
      expect(JSON.parse(options!.body as string).material_revision).toBe(2)
      return { draft: { ...newDraft(), headline: '最新标题', body: '最新资料正文', cover_title: '最新封面' }, request_id: 'fresh-source', material_id: 'parent-one', material_revision: 2 }
    }
    if (options?.method === 'PUT') saved = { ...saved, revision: saved.revision + 1, data: JSON.parse(options.body as string).data }
    return structuredClone(saved)
  })
  wrapper = mount(XhsDrafts, { props: { user: { id: 7, username: 'tester', role: 'admin', is_super_admin: true } },
    global: { stubs: { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true } } })
  const vm = wrapper.vm as unknown as { w: { readRoute: () => Promise<void> }; generate: () => Promise<void> }
  await vm.w.readRoute(); materialRevision = 2; await vm.generate()
  expect(saved.data.source_material_revision).toBe(2)
  expect(saved.data.body).toBe('最新资料正文')
  expect(window.confirm).not.toHaveBeenCalled()
})
