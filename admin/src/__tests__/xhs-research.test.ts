import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import XhsResearch from '../components/XhsResearch.vue'
import { bindResearchAccounts, selectionKey } from '../xhs-research-accounts'
import { CollectorError, type ResearchTask } from '../xhs-research'
import { uiStubs } from '../../../shared/test/ui-stubs'

const mocks = vi.hoisted(() => ({
  collect: vi.fn(), status: vi.fn(), toggle: vi.fn(), create: vi.fn(), remove: vi.fn(), fail: vi.fn(), get: vi.fn(),
  list: vi.fn(), open: vi.fn(), save: vi.fn(), start: vi.fn(),
  notes: vi.fn(), batches: vi.fn(), accounts: vi.fn(), cachedAccount: vi.fn(), openNote: vi.fn(),
}))
vi.mock('../xhs-accounts', () => ({ listXhsAccounts: mocks.accounts, openXhsNote: mocks.openNote }))
vi.mock('../xhs-research', async importOriginal => ({
  ...await importOriginal<typeof import('../xhs-research')>(),
  getCollectionAccount: mocks.cachedAccount, collectLocally: mocks.collect, getCollectorStatus: mocks.status, setCollectorEnabled: mocks.toggle, createResearchTask: mocks.create,
  deleteResearchTask: mocks.remove, failResearchTask: mocks.fail, getResearchTask: mocks.get,
  listResearchTasks: mocks.list, openCollectorBrowser: mocks.open, saveResearchResults: mocks.save,
  startResearchTask: mocks.start,
  listResearchNotes: mocks.notes, listResearchBatches: mocks.batches,
}))

const user = { id: 7, username: 'admin', role: 'admin', is_super_admin: true }
const base: ResearchTask = {
  id: 'task-1', grade: '四年级', subject: '数学', keyword: '', period: 'week', sort_by: 'popular',
  note_limit: 20, status: 'queued', note_count: 0, median_likes: null, average_likes: null,
  error: '', created_at: '2026-10-28 12:00:00', finished_at: '',
}
const note = { note_id: '65abcdef0123456789abcdef', title: '四年级找规律思维训练', author: '老师', published_text: '2天前',
  likes_text: '1.2万', likes_count: 12000, url: 'https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef',
  sort_rank: 1, captured_at: '2026-10-28T12:00:00Z' }
let wrapper: VueWrapper
let createdTask: ResearchTask
const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  localStorage.setItem(selectionKey, 'account-a')
  mocks.accounts.mockResolvedValue({ items: [
    { id: 'account-a', name: '数学账号', archived: false, busy: false },
    { id: 'account-b', name: '语文账号', archived: false, busy: false },
  ] })
  mocks.cachedAccount.mockResolvedValue('')
  mocks.openNote.mockResolvedValue({})
  mocks.status.mockResolvedValue({ connected: true, version: 10, enabled: true, busy: false })
  mocks.toggle.mockImplementation(async (enabled: boolean) => ({ connected: true, enabled, busy: false }))
  mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 })
  mocks.batches.mockResolvedValue({ items: [] })
  mocks.notes.mockResolvedValue({ items: [{ ...note, favorite: false, mark_status: '', remark: '', revision: 0, seen_count: 1, seen_before: false }], total: 1 })
  createdTask = base
  mocks.get.mockImplementation(async () => createdTask)
  mocks.create.mockImplementation(async (_id: number, input: Omit<ResearchTask, 'id' | 'status' | 'note_count' | 'median_likes' | 'average_likes' | 'error' | 'created_at' | 'finished_at'>) => {
    createdTask = { ...base, ...input }
    return createdTask
  })
  mocks.start.mockImplementation(async (_id: number, id: string) => ({ ...createdTask, id, status: 'running' }))
  mocks.collect.mockResolvedValue([note])
  mocks.save.mockResolvedValue({ ...base, status: 'completed', note_count: 1, median_likes: 12000, average_likes: 12000, items: [note] })
  mocks.fail.mockResolvedValue({ ...base, status: 'failed' })
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.restoreAllMocks() })

it('查看笔记使用当前选择的账号并保留完整链接，采集关闭也可查看', async () => {
  mocks.status.mockResolvedValue({ connected: true, version: 8, enabled: false, busy: false })
  const url = note.url + '?xsec_token=fixture-token&xsec_source=pc_search'
  mocks.notes.mockResolvedValue({ items: [{ ...note, url, favorite: false, mark_status: '', remark: '', revision: 0, seen_count: 1 }], total: 1 })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.get('select[aria-label="采集账号"]').setValue('account-b')
  await button('查看笔记').trigger('click'); await flushPromises()
  expect(mocks.openNote).toHaveBeenCalledWith('account-b', url)
  expect(wrapper.text()).toContain('已在「语文账号」的浏览器打开笔记')
  expect(mocks.open).not.toHaveBeenCalled()
})

it('未选择账号或打开失败时明确提示，不跳转到默认浏览器', async () => {
  localStorage.removeItem(selectionKey)
  mocks.status.mockResolvedValue({ connected: true, version: 8, enabled: true, busy: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises(); await button('查看笔记').trigger('click'); await flushPromises()
  expect(mocks.openNote).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('请先在采集条件中选择查看笔记使用的账号')
  await wrapper.get('select[aria-label="采集账号"]').setValue('account-a')
  mocks.openNote.mockRejectedValue(new Error('账号浏览器正在使用'))
  await button('查看笔记').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('账号浏览器正在使用')
  expect(wrapper.find('a[href="' + note.url + '"]').exists()).toBe(false)
})

it('让管理员按年级、科目、知识点和时间条件采集并查看笔记明细', async () => {
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.get('select[aria-label="年级"]').setValue('四年级')
  await button('更多筛选').trigger('click')
  await wrapper.get('select[aria-label="发布时间范围"]').setValue('week')
  await wrapper.get('input[aria-label="知识点或补充搜索词"]').setValue('找规律')
  expect((wrapper.get('input[aria-label="知识点或补充搜索词"]').element as HTMLInputElement).value).toBe('找规律')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(mocks.create).toHaveBeenCalledWith(7, expect.objectContaining({ grade: '四年级', subject: '数学', keyword: '找规律', period: 'week' }))
  expect(mocks.collect).toHaveBeenCalledWith(expect.objectContaining({ grade: '四年级', keyword: '找规律', status: 'running' }), 'account-a', expect.any(Function))
  expect(mocks.open).not.toHaveBeenCalled()
  expect(mocks.save).toHaveBeenCalledWith(7, 'task-1', [note])
  expect(wrapper.text()).toContain('采集完成')
  expect(wrapper.get('.xhs-result-table').text()).toContain(note.title)
  expect(wrapper.get('.xhs-result-table').text()).toContain(note.likes_text)
  expect(button('查看笔记').exists()).toBe(true)
  expect(wrapper.find('a[href="https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef"]').exists()).toBe(false)
})

it('本机采集器未运行时保留筛选表单并说明如何连接', async () => {
  mocks.status.mockResolvedValue({ connected: false, enabled: false, busy: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  expect(wrapper.text()).toContain('采集器未连接')
  expect(wrapper.text()).toContain('pnpm xhs:collector:setup')
  expect(button('开始采集').attributes('disabled')).toBeDefined()
  expect(mocks.create).not.toHaveBeenCalled()
})

it('页面打开时自动检测采集器连接变化', async () => {
  vi.useFakeTimers()
  mocks.status.mockResolvedValueOnce({ connected: true, version: 10, enabled: true, busy: false }).mockResolvedValue({ connected: false, enabled: false, busy: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  expect(wrapper.text()).toContain('采集器已开启')

  await vi.advanceTimersByTimeAsync(15000)
  await flushPromises()

  expect(wrapper.text()).toContain('采集器未连接')
})

it('用工作台按钮开启和关闭采集器', async () => {
  mocks.status.mockResolvedValue({ connected: true, version: 5, enabled: false, busy: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()

  await button('开启采集器').trigger('click')
  await flushPromises()

  expect(mocks.toggle).toHaveBeenCalledWith(true)
  expect(wrapper.text()).toContain('采集器已开启')
  expect(button('关闭采集器').exists()).toBe(true)
})

it('默认折叠发布时间、排序和数量筛选', async () => {
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()

  expect(wrapper.find('select[aria-label="发布时间范围"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('将搜索：一年级 数学 全部知识点')
  expect(wrapper.text()).toContain('一周内 · 最多点赞 · 每项最多 10 条')
  await button('更多筛选').trigger('click')
  expect(wrapper.find('select[aria-label="发布时间范围"]').exists()).toBe(true)
})

it('因平台限制暂停后仍能打开原账号；取消恢复确认不会开启采集器', async () => {
  mocks.status.mockResolvedValue({ connected: true, version: 10, enabled: false, busy: false, pause_reason: '小红书提示非真人操作，已停止采集。' })
  const confirm = vi.fn(() => false)
  window.confirm = confirm
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  expect(button('开始采集').attributes('disabled')).toBeDefined()
  await button('登录小红书').trigger('click'); await flushPromises()
  expect(mocks.open).toHaveBeenCalledWith('account-a')
  await button('开启采集器').trigger('click'); await flushPromises()
  expect(confirm).toHaveBeenCalled()
  expect(mocks.toggle).not.toHaveBeenCalled()
  confirm.mockReturnValue(true)
  await button('开启采集器').trigger('click'); await flushPromises()
  expect(mocks.toggle).toHaveBeenCalledWith(true, true)
})

it('非真人操作提示显示人工处理入口，不再次访问平台', async () => {
  mocks.collect.mockRejectedValue(new CollectorError('小红书提示非真人操作，已停止采集。', 'account_restricted'))
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(mocks.collect).toHaveBeenCalledOnce()
  expect(button('打开原页面检查').exists()).toBe(true)
  expect(mocks.save).not.toHaveBeenCalled()
})

it('原因不明的暂停说明不等同于账号风控，并提供原页面检查入口', async () => {
  mocks.collect.mockRejectedValue(new CollectorError('搜索页没有提供可读取的笔记，原因尚不明确。', 'collection_uncertain'))
  mocks.status.mockResolvedValue({ connected: true, version: 10, enabled: true, busy: false })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('原因尚不明确')
  expect(button('打开原页面检查').exists()).toBe(true)
  expect(mocks.collect).toHaveBeenCalledOnce()
  expect(mocks.save).not.toHaveBeenCalled()
})

it('采集历史按页从服务端读取', async () => {
  const firstPage = Array.from({ length: 10 }, (_, index) => ({ ...base, id: `task-${index + 1}` }))
  const secondPage = [{ ...base, id: 'task-11', grade: '高一' }, { ...base, id: 'task-12', grade: '高二' }]
  mocks.list.mockImplementation(async (page: number) => ({
    items: page === 1 ? firstPage : secondPage, total: 12, page, page_size: 10,
  }))
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()

  expect(wrapper.text()).toContain('12')
  await wrapper.findAll('button').find(item => item.text() === '下一页')!.trigger('click')
  await flushPromises()

  expect(mocks.list).toHaveBeenLastCalledWith(2, 10)
  expect(wrapper.text()).toContain('高二 · 数学')
})

it('笔记表格按点赞排序并分页展示', async () => {
  const notes = Array.from({ length: 12 }, (_, index) => ({
    ...note, note_id: `note-${index + 1}`, title: `标题 ${index + 1}`, likes_count: 12000 - index,
  }))
  mocks.get.mockResolvedValue({ ...base, status: 'completed', note_count: notes.length, items: notes })
  mocks.notes.mockImplementation(async ({ page = 1 }: { page?: number }) => ({ items: notes.slice((page - 1) * 10, page * 10).map(item => ({ ...item, favorite: false, mark_status: '', remark: '', revision: 0, seen_count: 1, seen_before: false })), total: notes.length }))
  mocks.list.mockResolvedValue({ items: [base], total: 1, page: 1, page_size: 10 })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.get('.task-row').trigger('click')
  await flushPromises()

  const firstPageRows = wrapper.findAll('.xhs-result-table tbody tr').map(row => row.text())
  expect(firstPageRows).toHaveLength(10)
  expect(firstPageRows[0]).toContain('标题 1')
  expect(firstPageRows[9]).toContain('标题 10')
  expect(firstPageRows.join(' ')).not.toContain('标题 11')
  await wrapper.findAll('button').find(item => item.text() === '下一页')!.trigger('click')
  await flushPromises()

  const secondPageRows = wrapper.findAll('.xhs-result-table tbody tr').map(row => row.text())
  expect(secondPageRows).toHaveLength(2)
  expect(secondPageRows[0]).toContain('标题 11')
  expect(secondPageRows[1]).toContain('标题 12')
})

it('删除历史最后一页的最后一条记录后返回前一页', async () => {
  const previousPage = Array.from({ length: 10 }, (_, index) => ({ ...base, id: `task-${index + 1}` }))
  const lastTask = { ...base, id: 'task-11', grade: '高三' }
  let remaining = 11
  mocks.list.mockImplementation(async (page: number) => page === 1
    ? { items: previousPage, total: remaining, page, page_size: 10 }
    : { items: [lastTask], total: remaining, page, page_size: 10 })
  mocks.remove.mockImplementation(async () => { remaining = 10 })
  mocks.get.mockResolvedValue(lastTask)
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '下一页')!.trigger('click')
  await flushPromises()
  await wrapper.get('.task-row').trigger('click')
  await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '删除记录')!.trigger('click')
  await flushPromises()

  expect(mocks.remove).toHaveBeenCalledWith(7, lastTask.id)
  expect(mocks.list).toHaveBeenLastCalledWith(1, 10)
  expect(wrapper.findAll('button').some(item => item.text() === '下一页')).toBe(false)
})

it('未选择或选择已归档账号时禁止新采集', async () => {
  localStorage.setItem(selectionKey, 'archived-account')
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  expect(button('开始采集').attributes('disabled')).toBeDefined()
  expect(localStorage.getItem(selectionKey)).toBe('')
  await wrapper.get('select[aria-label="采集账号"]').setValue('account-b')
  await button('登录小红书').trigger('click')
  expect(mocks.open).toHaveBeenCalledWith('account-b')
})

it('切换下拉框后，失败任务仍使用绑定原账号', async () => {
  createdTask = { ...base, status: 'failed' }
  bindResearchAccounts([base], 'account-a')
  mocks.list.mockResolvedValue({ items: [createdTask], total: 1, page: 1, page_size: 10 })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.get('select[aria-label="采集账号"]').setValue('account-b')
  await wrapper.get('.task-row').trigger('click'); await flushPromises()
  await button('重新运行').trigger('click'); await flushPromises()
  expect(mocks.collect).toHaveBeenCalledWith(expect.anything(), 'account-a', expect.any(Function))
})

it('找不到历史账号时取消绑定，不启动任务；旧服务也不能采集', async () => {
  window.confirm = vi.fn(() => false)
  createdTask = { ...base, status: 'failed' }
  mocks.list.mockResolvedValue({ items: [createdTask], total: 1, page: 1, page_size: 10 })
  wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(XhsResearch, { user })) }), { global: { stubs: uiStubs } })
  await flushPromises()
  await wrapper.get('.task-row').trigger('click'); await flushPromises()
  await button('重新运行').trigger('click'); await flushPromises()
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('数学账号'))
  expect(mocks.start).not.toHaveBeenCalled()
  mocks.status.mockResolvedValue({ connected: true, enabled: true, busy: false, version: 4 })
  await wrapper.get('button[aria-label="刷新采集器连接"]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('本机采集器需要更新')
  expect(button('开始采集').attributes('disabled')).toBeDefined()
})
