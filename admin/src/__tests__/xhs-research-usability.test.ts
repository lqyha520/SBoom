import { defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import XhsResearch from '../components/XhsResearch.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'

const api = vi.hoisted(() => ({ status: vi.fn(), tasks: vi.fn(), task: vi.fn(), batches: vi.fn(), accounts: vi.fn() }))
vi.mock('../xhs-research', async original => ({ ...await original<typeof import('../xhs-research')>(),
  getCollectorStatus: api.status, listResearchTasks: api.tasks, getResearchTask: api.task, listResearchBatches: api.batches,
}))
vi.mock('../xhs-accounts', async original => ({ ...await original<typeof import('../xhs-accounts')>(), listXhsAccounts: api.accounts }))
vi.mock('../components/XhsNoteLibrary.vue', () => ({ default: { template: '<div>笔记库</div>' } }))
const first = { id: 'first', grade: '一年级', subject: '数学', keyword: '口算', period: 'week', sort_by: 'popular', note_limit: 30,
  status: 'completed', note_count: 10, created_at: '2026-10-30T02:00:00Z' }
const second = { ...first, id: 'second', subject: '语文' }
const active = ref(true)
let wrapper: VueWrapper
beforeEach(() => {
  vi.useFakeTimers(); vi.resetAllMocks(); localStorage.clear(); active.value = true
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  api.status.mockResolvedValue({ connected: true, enabled: true, busy: false, version: 5 })
  api.tasks.mockResolvedValue({ items: [first, second], total: 2 }); api.batches.mockResolvedValue({ items: [] })
  api.accounts.mockResolvedValue({ items: [] })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => active.value ? h(XhsResearch, { user: { id: 1, username: 'admin', role: 'admin', is_super_admin: true } }) : null) }), { global: { stubs: uiStubs } })
})
afterEach(() => { wrapper.unmount(); vi.useRealTimers(); vi.restoreAllMocks() })

it('空闲时每15秒检查，隐藏页面及离开模块时暂停，恢复可见时立即检查', async () => {
  await flushPromises(); expect(api.status).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(5000); expect(api.status).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10000); expect(api.status).toHaveBeenCalledTimes(2)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true); document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(60000); expect(api.status).toHaveBeenCalledTimes(2)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
  expect(api.status).toHaveBeenCalledTimes(3)
  active.value = false; await nextTick(); await vi.advanceTimersByTimeAsync(30000)
  expect(api.status).toHaveBeenCalledTimes(3)
})

it('较慢的连接检查结束之前不叠加新的轮询', async () => {
  await flushPromises()
  let finish!: (result: unknown) => void
  api.status.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  await vi.advanceTimersByTimeAsync(15000); expect(api.status).toHaveBeenCalledTimes(2)
  await vi.advanceTimersByTimeAsync(45000); expect(api.status).toHaveBeenCalledTimes(2)
  finish({ connected: true, enabled: true, busy: false, version: 5 }); await flushPromises()
  await vi.advanceTimersByTimeAsync(15000); expect(api.status).toHaveBeenCalledTimes(3)
})

it('快速切换历史任务时，只显示最后点击的任务结果', async () => {
  await flushPromises()
  let finishFirst!: (result: unknown) => void, finishSecond!: (result: unknown) => void
  api.task.mockReturnValueOnce(new Promise(resolve => { finishFirst = resolve })).mockReturnValueOnce(new Promise(resolve => { finishSecond = resolve }))
  await wrapper.findAll('.task-row')[0]!.trigger('click'); await wrapper.findAll('.task-row')[1]!.trigger('click')
  finishSecond(second); await flushPromises(); expect(wrapper.get('.result-heading p').text()).toContain('语文')
  finishFirst(first); await flushPromises(); expect(wrapper.get('.result-heading p').text()).toContain('语文')
})

it('刷新历史后，已完成的采集任务会进入笔记结果而非停留在采集中', async () => {
  await flushPromises()
  api.task.mockResolvedValue({ ...first, status: 'running' })
  await wrapper.findAll('.task-row')[0]!.trigger('click'); await flushPromises()
  expect(wrapper.find('.result-state').exists()).toBe(true)
  await wrapper.get('button[aria-label="刷新采集历史"]').trigger('click'); await flushPromises()
  expect(wrapper.find('.result-state').exists()).toBe(false)
  expect(wrapper.text()).toContain('笔记库')
})
