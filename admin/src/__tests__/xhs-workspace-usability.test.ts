import { defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import XhsParentPicker from '../components/XhsParentPicker.vue'
import XhsPublicationCalendar from '../components/XhsPublicationCalendar.vue'
import XhsPublicationMedia from '../components/XhsPublicationMedia.vue'
import { newIdea, newPublication } from '../xhs-workflow'
import { localDay, weekStart } from '../xhs-workspace'
import { uiStubs } from '../../../shared/test/ui-stubs'

const api = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../api', () => ({ request: api.request }))
let wrapper: VueWrapper
const idea = { id: 'idea-one', kind: 'ideas', title: '口算练习', status: 'planned', revision: 1, parent_id: null,
  data: { ...newIdea(), grade: '一年级', subject: '数学', keyword: '口算' }, created_at: '', updated_at: '' }
const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
const calendar = (title: string) => ({ items: [{ ...idea, id: title, kind: 'publications', title, data: { ...newPublication(), account: '数学账号' },
  account_key: 'math', calendar_at: new Date(weekStart().getTime() + 10 * 3600000).toISOString(), conflicts: [] }], unscheduled: [],
  accounts: [{ id: 'math', name: '数学账号', last_published_at: new Date().toISOString() }] })
function picker() { wrapper = mount(XhsParentPicker, { props: { kind: 'ideas', next: 'materials' }, global: { stubs: uiStubs } }) }
function deferred() { let resolve!: (value: unknown) => void; const promise = new Promise(value => { resolve = value }); return { promise, resolve } }
beforeEach(() => { api.request.mockReset().mockResolvedValue({ items: [idea], total: 41 }) })
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks() })

it('关联搜索只提交一次，翻页使用已提交的词，并显示摘要状态', async () => {
  picker(); await flushPromises()
  expect(wrapper.text()).toContain('一年级 · 数学 · 口算')
  await button('下一页').trigger('click'); await flushPromises(); api.request.mockClear()
  await wrapper.get('input').setValue('  口算  ')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.request).toHaveBeenCalledTimes(1)
  expect(api.request.mock.lastCall![0]).toContain('q=%E5%8F%A3%E7%AE%97&page=1')
  await wrapper.get('input').setValue('还未提交')
  await button('下一页').trigger('click'); await flushPromises()
  expect(api.request.mock.lastCall![0]).toContain('q=%E5%8F%A3%E7%AE%97&page=2')
})

it('关联内容刷新期间不能选择旧内容，失败有重试，末页缩小时回退', async () => {
  picker(); await flushPromises()
  const pending = deferred(); api.request.mockReturnValueOnce(pending.promise)
  await wrapper.get('form').trigger('submit')
  expect(wrapper.find('.workflow-list-item').exists()).toBe(false)
  pending.resolve({ items: [idea], total: 41 }); await flushPromises()
  api.request.mockRejectedValueOnce(new Error('读取失败'))
  await button('下一页').trigger('click'); await flushPromises()
  expect(wrapper.find('.workflow-list-item').exists()).toBe(false)
  api.request.mockResolvedValue({ items: [idea], total: 1 })
  await button('重新加载').trigger('click'); await flushPromises()
  expect(api.request.mock.lastCall![0]).toContain('page=1')
  expect(wrapper.find('.workflow-list-item').exists()).toBe(true)
})

it('日历加载或失败时不显示空安排结论，重试恢复安排', async () => {
  const pending = deferred(); api.request.mockReturnValueOnce(pending.promise)
  wrapper = mount(XhsPublicationCalendar, { global: { stubs: uiStubs } })
  expect(wrapper.text()).toContain('正在读取发布安排')
  expect(wrapper.text()).not.toContain('暂无安排')
  expect(wrapper.text()).not.toContain('所有进行中的发布计划都已排期')
  pending.resolve(calendar('口算发布')); await flushPromises()
  expect(wrapper.text()).toContain('口算发布')
  expect(wrapper.get('.publication-calendar article').text()).toContain('口算发布')
  expect(wrapper.get('input[type=date]').element).toHaveProperty('value', localDay(weekStart()))
  api.request.mockRejectedValueOnce(new Error('服务暂不可用'))
  await button('刷新日历').trigger('click'); await flushPromises()
  expect(wrapper.text()).not.toContain('口算发布')
  expect(wrapper.text()).not.toContain('暂无安排')
  api.request.mockResolvedValue(calendar('恢复发布'))
  await button('重新加载日历').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('恢复发布')
})

it('快速切周只显示最后的安排，账号筛选同时影响排期与未排期', async () => {
  api.request.mockResolvedValue(calendar('初始发布'))
  wrapper = mount(XhsPublicationCalendar, { global: { stubs: uiStubs } }); await flushPromises()
  const first = deferred(), second = deferred()
  api.request.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
  await button('下一周').trigger('click'); await button('下一周').trigger('click')
  second.resolve({ ...calendar('最新发布'), items: [], unscheduled: calendar('最新发布').items }); await flushPromises()
  first.resolve(calendar('过期发布')); await flushPromises()
  expect(wrapper.text()).not.toContain('过期发布')
  expect(wrapper.text()).toContain('最新发布')
  api.request.mockResolvedValue({ ...calendar('最新发布'), items: [], unscheduled: calendar('最新发布').items, unscheduled_total: 1 })
  await wrapper.get('select').setValue('math'); await flushPromises()
  expect(wrapper.text()).toContain('尚未排期 · 1 项')
  expect(api.request.mock.lastCall![0]).toContain('account=math')
})

it('未排期分页保留账号筛选，切换账号回到第一页；服务器回退页码不重复读取', async () => {
  api.request.mockResolvedValue({ ...calendar('计划'), unscheduled_total: 25, unscheduled_page: 1 })
  wrapper = mount(XhsPublicationCalendar, { global: { stubs: uiStubs } }); await flushPromises()
  const vm = wrapper.vm as unknown as { pendingPage: number; account: string }
  vm.pendingPage = 2
  api.request.mockResolvedValueOnce({ ...calendar('第二页'), unscheduled_total: 25, unscheduled_page: 2 })
  await flushPromises()
  expect(api.request.mock.lastCall![0]).toContain('unscheduled_page=2')
  vm.account = 'math'; await flushPromises()
  expect(api.request.mock.lastCall![0]).toContain('account=math&unscheduled_page=1')
  api.request.mockResolvedValueOnce({ ...calendar('回退页'), unscheduled_total: 10, unscheduled_page: 1 })
  api.request.mockClear(); vm.pendingPage = 2; await flushPromises()
  expect(vm.pendingPage).toBe(1)
  expect(api.request).toHaveBeenCalledTimes(1)
})

it.each([XhsParentPicker, XhsPublicationCalendar])('离开缓存页面后未完成请求不会更新内容', async component => {
  const shown = ref(true), pending = deferred()
  api.request.mockReturnValueOnce(pending.promise)
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => shown.value ? h(component, { kind: 'ideas', next: 'materials' }) : null) }), { global: { stubs: uiStubs } })
  shown.value = false; await nextTick()
  pending.resolve({ ...calendar('过期发布'), total: 1 }); await flushPromises()
  api.request.mockResolvedValue(component === XhsParentPicker ? { items: [idea], total: 1 } : calendar('最新发布'))
  shown.value = true; await nextTick()
  expect(wrapper.text()).not.toContain('过期发布')
  await flushPromises()
  expect(wrapper.text()).toContain(component === XhsParentPicker ? '口算练习' : '最新发布')
})

it('配图前后移动复用预览，移除只释放被移除文件，离开释放剩余文件', async () => {
  const create = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => 'blob:' + (blob as File).name)
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  wrapper = mount(XhsPublicationMedia, { props: { modelValue: [], owner: 7 }, global: { stubs: uiStubs } })
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['a'], 'a.png', { type: 'image/png' }), new File(['b'], 'b.png', { type: 'image/png' })] })
  await input.trigger('change'); await flushPromises()
  expect(create).toHaveBeenCalledTimes(2)
  await wrapper.get('button[aria-label="后移图片 1"]').trigger('click')
  expect(wrapper.findAll('img').map(image => image.attributes('src'))).toEqual(['blob:b.png', 'blob:a.png'])
  expect(create).toHaveBeenCalledTimes(2); expect(revoke).not.toHaveBeenCalled()
  await wrapper.get('button[aria-label="移除图片 1"]').trigger('click')
  expect(revoke).toHaveBeenCalledExactlyOnceWith('blob:b.png')
  expect(create).toHaveBeenCalledTimes(2)
  wrapper.unmount(); expect(revoke).toHaveBeenLastCalledWith('blob:a.png')
})
