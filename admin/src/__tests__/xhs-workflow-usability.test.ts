import { defineComponent, h, nextTick, KeepAlive, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { adminRoute } from '../navigation'
import { newIdea, useWorkflow } from '../xhs-workflow'
import XhsWorkflowFrame from '../components/XhsWorkflowFrame.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'

const api = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../api', () => ({ request: api.request }))
let wrapper: VueWrapper, workflow: ReturnType<typeof useWorkflow<ReturnType<typeof newIdea>>>
const active = ref(true)
const record = { id: 'one', kind: 'ideas', parent_id: null, title: '找规律', status: 'inbox', revision: 1,
  data: { ...newIdea(), title: '找规律' }, created_at: '2026-10-30T02:00:00Z', updated_at: '2026-10-30T02:00:00Z' }
function start() {
  const component = defineComponent({ setup() { workflow = useWorkflow('ideas', newIdea, () => {}, 1); void workflow.readRoute(); return () => h('div') } })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => active.value ? h(component) : null) }))
}
beforeEach(() => {
  active.value = true; localStorage.clear(); Object.assign(adminRoute, { tab: 'xhsIdeas', query: '' })
  api.request.mockReset().mockResolvedValue({ items: [record], total: 41, page: 1, page_size: 20 })
})
afterEach(() => wrapper?.unmount())

it('搜索从第一页开始且只请求一次，翻页沿用已提交的关键词', async () => {
  start(); await flushPromises()
  workflow.page.value = 2; await flushPromises(); api.request.mockClear()
  workflow.q.value = '  口算  '; workflow.loadList(); await flushPromises()
  expect(api.request).toHaveBeenCalledTimes(1)
  expect(api.request.mock.calls[0]![0]).toContain('q=%E5%8F%A3%E7%AE%97&status=&page=1')
  workflow.q.value = '尚未提交'; workflow.page.value = 2; await flushPromises()
  expect(api.request.mock.lastCall![0]).toContain('q=%E5%8F%A3%E7%AE%97&status=&page=2')
})

it('同时清空关键词、状态和页码不会重复读取；重试成功清除错误', async () => {
  start(); await flushPromises()
  workflow.filter.value = 'planned'; await flushPromises()
  workflow.page.value = 2; await flushPromises(); api.request.mockClear()
  workflow.resetFilters(); await flushPromises()
  expect(api.request).toHaveBeenCalledTimes(1)
  expect(api.request.mock.lastCall![0]).toContain('q=&status=&page=1')
  api.request.mockRejectedValueOnce(new Error('临时不可用'))
  await workflow.loadList(); expect(workflow.error.value).toBe('临时不可用')
  await workflow.loadList(); expect(workflow.error.value).toBe('')
})

it('切换到其他模块后，未完成的列表请求不能更新缓存页面', async () => {
  start(); await flushPromises()
  let resolve!: (value: unknown) => void
  api.request.mockReturnValueOnce(new Promise(value => { resolve = value }))
  const pending = workflow.loadList(); await nextTick()
  active.value = false; await nextTick()
  resolve({ items: [{ ...record, title: '过期结果' }], total: 1 }); await pending
  expect(workflow.items.value[0]?.title).toBe('找规律')
  expect(workflow.loading.value).toBe(false)
})

it('保存快捷键尊重弹窗、加载状态和组件停用', async () => {
  const saved = vi.fn()
  wrapper = mount(XhsWorkflowFrame, { props: { title: '选题库', description: '', editing: true, loading: false, busy: false,
    error: '', notice: '', dirty: true, items: [], total: 0, page: 1, statuses: ['inbox'] }, attrs: { onSave: saved }, global: { stubs: uiStubs } })
  const key = () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true, cancelable: true }))
  key(); expect(wrapper.emitted('save')).toHaveLength(1)
  const modal = document.createElement('div'); modal.setAttribute('role', 'dialog'); document.body.append(modal)
  key(); expect(wrapper.emitted('save')).toHaveLength(1); modal.remove()
  await wrapper.setProps({ loading: true }); key(); expect(wrapper.emitted('save')).toHaveLength(1)
  await wrapper.setProps({ loading: false, editing: false }); key(); expect(wrapper.emitted('save')).toHaveLength(1)
  await wrapper.setProps({ editing: true }); wrapper.unmount(); key(); expect(saved).toHaveBeenCalledTimes(1)
})
