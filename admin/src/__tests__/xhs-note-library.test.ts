import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import XhsNoteLibrary from '../components/XhsNoteLibrary.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import type { LibraryNote } from '../xhs-research'

const api = vi.hoisted(() => ({ list: vi.fn(), mark: vi.fn(), history: vi.fn(), export: vi.fn(), download: vi.fn() }))
vi.mock('../xhs-research', async original => ({ ...await original<typeof import('../xhs-research')>(),
  listResearchNotes: api.list, saveNoteMark: api.mark, getNoteHistory: api.history, exportResearchNotes: api.export,
}))
vi.mock('../../../shared/download', () => ({ downloadBlob: api.download }))
const note = { note_id: '65abcdef0123456789abcdef', title: '一年级口算', author: '王老师', published_text: '昨天',
  likes_count: 200, likes_text: '200', url: 'https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef', captured_at: '',
  favorite: false, mark_status: '', remark: '', revision: 0, seen_count: 2, seen_before: true, grade: '一年级', subject: '数学', keyword: '口算' } as LibraryNote
let wrapper: VueWrapper
const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => {
  vi.resetAllMocks()
  api.list.mockResolvedValue({ items: [{ ...note }], total: 1 })
  api.mark.mockResolvedValue({ favorite: true, mark_status: 'planned', remark: '周末做', revision: 1 })
  api.history.mockResolvedValue({ items: [{ ...note, task_id: 'previous' }], total: 1 })
  api.export.mockResolvedValue(new Blob(['xlsx']))
  wrapper = mount(XhsNoteLibrary, { props: { adminId: 1, taskId: 'task-one' }, global: { stubs: uiStubs } })
})
afterEach(() => wrapper.unmount())

it('筛选条件作用于当前任务并可切换到跨任务收藏', async () => {
  await flushPromises()
  await wrapper.get('input[aria-label="搜索笔记标题"]').setValue('口算')
  await wrapper.get('input[aria-label="筛选作者"]').setValue('王')
  await wrapper.get('input[aria-label="最低点赞数"]').setValue('100')
  await wrapper.get('input[aria-label="排除关键词"]').setValue('招生,卖课')
  await wrapper.get('form.note-filters').trigger('submit'); await flushPromises()
  expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ task_id: 'task-one', q: '口算', author: '王', min_likes: 100, exclude: '招生,卖课' }))
  await button('我的收藏').trigger('click'); await flushPromises()
  expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ task_id: '', favorite_only: true }))
})

it('收藏与备注带管理员身份和当前版本保存', async () => {
  await flushPromises()
  await button('收藏').trigger('click'); await flushPromises()
  expect(api.mark).toHaveBeenCalledWith(1, expect.objectContaining({ note_id: note.note_id }), { favorite: true })
  await wrapper.get(`button[aria-label="编辑标记和备注：${note.title}"]`).trigger('click')
  await wrapper.get('textarea[aria-label="笔记备注"]').setValue('改成趣味口算')
  await wrapper.get('select[aria-label="笔记选题状态"]').setValue('done')
  await wrapper.get('form#xhs-note-mark').trigger('submit'); await flushPromises()
  expect(api.mark).toHaveBeenLastCalledWith(1, expect.objectContaining({ revision: 1 }), expect.objectContaining({ mark_status: 'done', remark: '改成趣味口算' }))
})

it('只导出当前筛选下选中的笔记，切换筛选后清除选择', async () => {
  await flushPromises()
  await wrapper.get('input[aria-label="选择本页全部笔记"]').setValue(true)
  await button('导出选中 (1)').trigger('click'); await flushPromises()
  expect(api.export).toHaveBeenCalledWith(1, expect.objectContaining({ task_id: 'task-one' }), [note.note_id])
  expect(api.download).toHaveBeenCalledWith(expect.any(Blob), expect.stringMatching(/\.xlsx$/), 2000)
  await button('全部笔记').trigger('click'); await flushPromises()
  expect(wrapper.text()).not.toContain('导出选中 (1)')
})

it('重复笔记可查看历次点赞记录', async () => {
  await flushPromises()
  await wrapper.get(`button[aria-label="查看点赞记录：${note.title}"]`).trigger('click'); await flushPromises()
  expect(api.history).toHaveBeenCalledWith(note.note_id, 1)
  expect(wrapper.get('[role="dialog"]').text()).toContain('200 赞')
})

it('版本冲突时保留编辑内容并显示原因', async () => {
  api.mark.mockRejectedValue(new Error('已在其他页面更新，请刷新后重试'))
  await flushPromises()
  await wrapper.get(`button[aria-label="编辑标记和备注：${note.title}"]`).trigger('click')
  await wrapper.get('textarea').setValue('保留这段备注')
  await wrapper.get('form#xhs-note-mark').trigger('submit'); await flushPromises()
  expect(wrapper.get('[role="dialog"]').text()).toContain('已在其他页面更新')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('保留这段备注')
})

it('切换任务和范围时只读取一次，避免重复加载并清空旧选择', async () => {
  await flushPromises()
  await wrapper.get('input[aria-label="选择本页全部笔记"]').setValue(true)
  api.list.mockClear()
  await wrapper.setProps({ taskId: 'task-two', refreshKey: 1 }); await flushPromises()
  expect(api.list).toHaveBeenCalledTimes(1)
  expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ task_id: 'task-two', page: 1 }))
  expect(wrapper.text()).not.toContain('导出选中 (1)')
  await button('全部笔记').trigger('click'); await flushPromises(); api.list.mockClear()
  await wrapper.setProps({ taskId: 'task-three' }); await flushPromises()
  expect(api.list).toHaveBeenCalledTimes(1)
  expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ task_id: 'task-three', page: 1 }))
})

it('查看笔记交由账号浏览器处理，传递完整链接，打开期间禁止重复点击', async () => {
  await flushPromises()
  await wrapper.setProps({ noteAccountName: '数学账号' })
  await button('查看笔记').trigger('click')
  expect(wrapper.emitted('openNote')?.[0]).toEqual([expect.objectContaining({ note_id: note.note_id, url: note.url })])
  expect(wrapper.text()).toContain('查看笔记使用「数学账号」的账号浏览器')
  await wrapper.setProps({ openingNoteId: note.note_id })
  expect(button('查看笔记').attributes('disabled')).toBeDefined()
  expect(wrapper.find(`a[href="${note.url}"]`).exists()).toBe(false)
})

it('收起条件后展示已生效筛选，尚未提交的输入不影响提示，重置移除提示', async () => {
  await flushPromises()
  await wrapper.get('input[aria-label="筛选作者"]').setValue('王老师')
  await wrapper.get('input[aria-label="最低点赞数"]').setValue('100')
  expect(wrapper.find('.applied-filters').exists()).toBe(false)
  await wrapper.get('form.note-filters').trigger('submit'); await flushPromises()
  expect(wrapper.get('.applied-filters').text()).toContain('作者：王老师')
  expect(wrapper.get('.applied-filters').text()).toContain('点赞 ≥ 100')
  await wrapper.get('input[aria-label="筛选作者"]').setValue('未提交的作者')
  expect(wrapper.get('.applied-filters').text()).not.toContain('未提交的作者')
  await button('重置').trigger('click'); await flushPromises()
  expect(wrapper.find('.applied-filters').exists()).toBe(false)
})

it('关闭未保存备注时先确认，继续编辑保留内容，明确放弃后关闭', async () => {
  await flushPromises()
  await wrapper.get(`button[aria-label="编辑标记和备注：${note.title}"]`).trigger('click')
  await wrapper.get('textarea').setValue('不能丢失的备注')
  await button('取消').trigger('click')
  expect(wrapper.text()).toContain('放弃未保存的备注？')
  await button('继续编辑').trigger('click')
  expect(wrapper.get('textarea').element).toHaveProperty('value', '不能丢失的备注')
  await button('取消').trigger('click'); await button('放弃修改').trigger('click')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(api.mark).not.toHaveBeenCalled()
})
