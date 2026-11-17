import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { ApiError } from '../api'
import { adminRoute } from '../navigation'
import { newIdea, newPublication, useWorkflow, type WorkflowRecord, type IdeaData } from '../xhs-workflow'
import { useXhsGeneration } from '../xhs-generation'
import XhsAnalytics from '../components/XhsAnalytics.vue'
import XhsWorkflowVersions from '../components/XhsWorkflowVersions.vue'

const api = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: api.request }))
let wrapper: VueWrapper
beforeEach(() => { localStorage.clear(); api.request.mockReset(); window.confirm = vi.fn(() => false) })
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals(); localStorage.clear() })
function entry(id: string, data: IdeaData, revision = 1): WorkflowRecord<IdeaData> {
  return { id, kind: 'ideas', parent_id: null, title: data.title, status: data.status, revision, data, created_at: '', updated_at: '' }
}
async function newEditor() {
  Object.assign(adminRoute, { tab: 'xhsIdeas', query: 'new=1' })
  let workflow!: ReturnType<typeof useWorkflow<IdeaData>>
  wrapper = mount(defineComponent({ setup() { workflow = useWorkflow('ideas', newIdea, () => {}, 7); return () => h('div') } }))
  await workflow.readRoute(); await flushPromises()
  return workflow
}

it('新建响应丢失后查询原记录，确认保存成功而不重复创建', async () => {
  let saved!: WorkflowRecord<IdeaData>
  api.request.mockImplementation(async (_path, init?: RequestInit) => {
    if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); saved = entry(body.id, body.data); throw new Error('请求超时') }
    return saved
  })
  const w = await newEditor(); w.data.value.title = '原提交'
  expect(await w.save()).toBe(true)
  expect(w.record.value?.id).toBe(saved.id)
  expect(adminRoute.query).toBe('id=' + saved.id)
  expect(w.notice.value).toContain('原提交保存成功')
  expect(api.request.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
})

it('保存和查询都超时后，再次保存先恢复原记录并保留后续编辑', async () => {
  let saved!: WorkflowRecord<IdeaData>, queryFails = true
  api.request.mockImplementation(async (_path, init?: RequestInit) => {
    if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); saved = entry(body.id, body.data); throw new Error('请求超时') }
    if (init?.method === 'PUT') { const body = JSON.parse(String(init.body)); saved = entry(saved.id, body.data, body.revision + 1); return saved }
    if (queryFails) throw new Error('查询暂时失败')
    return saved
  })
  const w = await newEditor(); w.data.value.title = '原提交'
  expect(await w.save()).toBe(false)
  w.data.value.title = '超时后修改'; queryFails = false
  expect(await w.save()).toBe(false)
  expect(w.record.value?.data.title).toBe('原提交')
  expect(w.data.value.title).toBe('超时后修改')
  expect(w.dirty.value).toBe(true)
  expect(w.notice.value).toContain('之后的编辑已保留')
  await flushPromises()
  expect(await w.save()).toBe(true)
  expect(saved.data.title).toBe('超时后修改')
  expect(api.request.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
})

it('后台尚未查询到原新建时，重试沿用原编号和原内容', async () => {
  let saved: WorkflowRecord<IdeaData> | null = null, attempts = 0
  api.request.mockImplementation(async (_path, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); attempts++
      if (attempts === 1) throw new Error('请求超时')
      saved = entry(body.id, body.data); return saved
    }
    if (!saved) throw new ApiError('不存在', 404)
    return saved
  })
  const w = await newEditor(); w.data.value.title = '原内容'; expect(await w.save()).toBe(false)
  w.data.value.title = '后来修改'; expect(await w.save()).toBe(false)
  const writes = api.request.mock.calls.filter(([, init]) => init?.method === 'POST').map(([, init]) => JSON.parse(init.body))
  expect(writes[1]).toEqual(writes[0])
  expect(w.data.value.title).toBe('后来修改')
  expect(w.record.value?.data.title).toBe('原内容')
})

it('保存等待期间的编辑不会被返回结果覆盖', async () => {
  let complete!: (value: WorkflowRecord<IdeaData>) => void, body!: { id: string; data: IdeaData }
  api.request.mockImplementation((_path, init?: RequestInit) => { body = JSON.parse(String(init?.body)); return new Promise(resolve => { complete = resolve }) })
  const w = await newEditor(); w.data.value.title = '提交内容'; const pending = w.save()
  w.data.value.title = '新编辑'; complete(entry(body.id, body.data)); expect(await pending).toBe(false)
  expect(w.data.value.title).toBe('新编辑'); expect(w.dirty.value).toBe(true)
})

it('更新响应丢失可核对服务端去除空白后的保存结果', async () => {
  const w = await newEditor(); w.data.value.title = '标题'
  api.request.mockImplementation(async (_path, init?: RequestInit) => { const body = JSON.parse(String(init?.body)); return entry(body.id, body.data) })
  expect(await w.save()).toBe(true); await flushPromises()
  const id = w.record.value!.id
  w.data.value.notes = ' 新备注 '
  const saved = entry(id, { ...w.data.value, notes: '新备注' }, 2)
  api.request.mockImplementation(async (_path, init?: RequestInit) => { if (init?.method === 'PUT') throw new Error('响应丢失'); return saved })
  expect(await w.save()).toBe(true); expect(w.data.value.notes).toBe('新备注')
})

it('另一窗口更新了不同内容时保留输入，不误判原提交成功', async () => {
  const w = await newEditor(); w.data.value.title = '标题'
  api.request.mockImplementation(async (_path, init?: RequestInit) => { const body = JSON.parse(String(init?.body)); return entry(body.id, body.data) })
  await w.save(); await flushPromises(); w.data.value.notes = '我的编辑'
  const latest = entry(w.record.value!.id, { ...w.data.value, notes: '其他窗口内容' }, 2)
  api.request.mockImplementation(async (_path, init?: RequestInit) => { if (init?.method === 'PUT') throw new ApiError('版本冲突', 409); return latest })
  expect(await w.save()).toBe(false); expect(w.data.value.notes).toBe('我的编辑'); expect(w.record.value?.revision).toBe(1)
  expect(w.error.value).toContain('其他页面更新')
})

it('明确的输入校验失败后允许修改内容重新保存', async () => {
  const w = await newEditor(); w.data.value.title = '不合要求'
  api.request.mockRejectedValueOnce(new ApiError('请修改标题', 422))
  expect(await w.save()).toBe(false); w.data.value.title = '修正标题'
  api.request.mockImplementation(async (_path, init?: RequestInit) => { const body = JSON.parse(String(init?.body)); return entry(body.id, body.data) })
  expect(await w.save()).toBe(true); expect(w.record.value?.title).toBe('修正标题')
})

it('清除本机生成记录失败也能结束跟踪，切回记录不会再次锁住生成', async () => {
  let generation!: ReturnType<typeof useXhsGeneration<{ value: string }>>, id = 'record-a'
  const { ref } = await import('vue'); const recordId = ref(id)
  wrapper = mount(defineComponent({ setup() { generation = useXhsGeneration(7, () => recordId.value, 'material'); return () => h('div') } }))
  api.request.mockResolvedValueOnce({ revision: '1', timeout_ms: 1000 }).mockResolvedValueOnce({ value: '结果' })
  await generation.generate('/generate', {})
  const storage = localStorage
  vi.stubGlobal('localStorage', { getItem: storage.getItem.bind(storage), setItem: storage.setItem.bind(storage), removeItem: () => { throw new Error('存储不可用') } })
  expect(() => generation.finish()).not.toThrow(); expect(generation.pending.value).toBeNull(); expect(generation.error.value).toContain('未能清除')
  recordId.value = 'record-b'; await flushPromises(); recordId.value = id; await flushPromises()
  expect(generation.pending.value).toBeNull()
  api.request.mockResolvedValueOnce({ revision: '1', timeout_ms: 1000 }).mockResolvedValueOnce({ value: '新结果' })
  expect(await generation.generate('/generate', {})).toEqual({ value: '新结果' })
})

it('历史版本先显示当前编辑差异，拒绝覆盖时不替换内容', async () => {
  const old = { ...newIdea(), title: '旧标题', notes: '旧备注' }, current = { ...newIdea(), title: '未保存的新标题', notes: '当前备注' }
  api.request.mockResolvedValue({ items: [{ revision: 1, data: old, created_at: '' }], total: 1 })
  wrapper = mount(XhsWorkflowVersions, { props: { record: entry('one', { ...newIdea(), title: '已保存标题' }, 2), current, dirty: true }, global: { stubs: uiStubs } })
  await wrapper.findAll('button').find(item => item.text() === '版本历史')!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '带入编辑')!.trigger('click')
  expect(wrapper.text()).toContain('未保存的新标题'); expect(wrapper.text()).toContain('旧标题'); expect(wrapper.emitted('restore')).toBeUndefined()
  await wrapper.findAll('button').find(item => item.text() === '确认带入编辑')!.trigger('click')
  expect(window.confirm).toHaveBeenCalledOnce(); expect(wrapper.emitted('restore')).toBeUndefined()
  vi.mocked(window.confirm).mockReturnValue(true)
  await wrapper.findAll('button').find(item => item.text() === '确认带入编辑')!.trigger('click')
  expect(wrapper.emitted('restore')?.[0]?.[0]).toEqual(old)
})

async function reviewEditor() {
  Object.assign(adminRoute, { tab: 'xhsAnalytics', query: 'id=pub-one&checkpoint=7' })
  wrapper = mount(XhsAnalytics, { props: { user: { id: 7, role: 'admin', is_super_admin: true, username: 'review' } }, global: { stubs: { ...uiStubs, XhsReviewIdeas: true } } })
  await (wrapper.vm as unknown as { load: () => Promise<void> }).load(); await flushPromises()
}
const published = () => ({ id: 'pub-one', kind: 'publications', revision: 1, parent_id: null, status: 'published', title: '发布记录', data: { ...newPublication(), title: '发布记录', status: 'published', published_at: new Date().toISOString(), url: 'https://xhslink.com/a/one' }, created_at: '', updated_at: '' })
it('复盘通过一个接口保存，冲突时统计和结论均保持原输入', async () => {
  const record = published()
  api.request.mockImplementation(async (path: string, init?: RequestInit) => { if (init?.method === 'PUT') throw new ApiError('复盘尚未保存', 409); return path.includes('/metrics/') ? { items: [] } : record })
  await reviewEditor(); const editor = wrapper.vm as unknown as { conclusion: string; form: { revision: number; views: number } }
  editor.conclusion = '新结论'; editor.form.views = 123
  await wrapper.findAll('button').find(item => item.text() === '保存复盘')!.trigger('click'); await flushPromises()
  const writes = api.request.mock.calls.filter(([, init]) => init?.method === 'PUT')
  expect(writes.map(([path]) => path)).toEqual(['/api/v1/admin/xhs-workflow/reviews/pub-one'])
  expect(editor.conclusion).toBe('新结论'); expect(editor.form.views).toBe(123); expect(editor.form.revision).toBe(0)
  expect(wrapper.text()).toContain('复盘尚未保存')
})

it('复盘提交响应丢失后查询确认两部分已保存', async () => {
  let record = published(), items: unknown[] = []
  api.request.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body)); record = { ...record, revision: 2, data: { ...record.data, conclusion: body.conclusion, next_action: body.next_action } }
      items = [{ ...body.metric, revision: 1 }]; throw new Error('响应超时')
    }
    return path.includes('/metrics/') ? { items } : record
  })
  await reviewEditor(); const editor = wrapper.vm as unknown as { conclusion: string; form: { revision: number; views: number }; dirty: boolean }
  editor.conclusion = '有用的结论'; editor.form.views = 200
  await wrapper.findAll('button').find(item => item.text() === '保存复盘')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('原复盘完整保存成功'); expect(editor.form.revision).toBe(1); expect(editor.dirty).toBe(false)
})
