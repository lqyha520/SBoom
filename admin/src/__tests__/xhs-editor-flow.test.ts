import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { adminRoute, navigateAdmin } from '../navigation'
import { newDraft, newMaterial } from '../xhs-workflow'
import XhsDrafts from '../components/XhsDrafts.vue'
import XhsMaterials from '../components/XhsMaterials.vue'
import XhsContentNavigation from '../components/XhsContentNavigation.vue'
const mocks = vi.hoisted(() => ({ request: vi.fn(), images: vi.fn(), download: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: mocks.request }))
vi.mock('../xhs-content-export', async original => ({ ...await original<typeof import('../xhs-content-export')>(), draftImages: mocks.images }))
vi.mock('../../../shared/download', () => ({ downloadBlob: mocks.download }))
let wrapper: VueWrapper
const records = ['a','b'].map(id => ({ id: `draft-${id}`, kind: 'drafts', parent_id: 'material-one', title: `笔记${id}`, revision: 1, status: 'draft',
  data: { ...newDraft(), title: `笔记${id}`, headline: `标题${id}`, cover_title: `封面${id}`, body: `正文${id}` }, created_at: '', updated_at: '' }))
const material = { id: 'material-one', kind: 'materials', revision: 1, status: 'draft', title: '资料', parent_id: 'idea-one',
  data: { ...newMaterial(), title: '资料', questions: [{ stem: '1+1=?', answer: '2', analysis: '一加一等于二', options: [], quality_issues: [] }] } }
const stubs = { ...uiStubs, XhsWorkflowLinks: true, XhsWorkflowVersions: true, XhsProfilePicker: true }
type Editor = { w: { readRoute: () => Promise<void> }; data: ReturnType<typeof newDraft>; preview: string[]; step: string; previewImages: () => Promise<void> }
function editor() { return wrapper.vm as unknown as Editor }
beforeEach(() => {
  localStorage.clear(); window.confirm = vi.fn(() => true)
  mocks.request.mockReset().mockImplementation(async (path: string) => {
    if (path.includes('idea-one')) return { id: 'idea-one', kind: 'ideas', title: '选题', data: { title: '选题' } }
    if (path.includes('material-one')) return structuredClone(material)
    if (path.endsWith('draft-a')) return structuredClone(records[0])
    if (path.endsWith('draft-b')) return structuredClone(records[1])
    return { items: [], total: 0 }
  })
  mocks.images.mockReset().mockResolvedValue([new Blob(['preview-a'], { type: 'image/png' })])
  mocks.download.mockReset()
})
afterEach(() => { wrapper?.unmount(); localStorage.clear() })
async function openDraft() {
  Object.assign(adminRoute, { tab: 'xhsDrafts', query: 'id=draft-a' })
  wrapper = mount(XhsDrafts, { props: { user: { id: 7, username: 'review', role: 'admin', is_super_admin: true } }, global: { stubs } })
  await editor().w.readRoute(); await flushPromises()
}
it('修改封面后清除旧预览，提示重新生成', async () => {
  await openDraft(); editor().step = 'preview'; await editor().previewImages(); await flushPromises()
  const previous = editor().preview[0]
  editor().data.cover_title = '已经修改的封面'; await flushPromises()
  expect(previous).toBeTruthy()
  expect(editor().preview).toEqual([])
  expect(wrapper.find('img[alt="封面预览"]').exists()).toBe(false)
})
it('切换笔记后回到正文步骤并清除上条配图', async () => {
  await openDraft(); editor().step = 'preview'; await editor().previewImages(); const previous = editor().preview[0]
  Object.assign(adminRoute, { query: 'id=draft-b' }); await flushPromises()
  expect(editor().data.title).toBe('笔记b')
  expect(previous).toBeTruthy()
  expect(editor().step).toBe('copy')
  expect(editor().preview).toEqual([])
})
it('上一条笔记的慢预览结果不能写入新笔记', async () => {
  await openDraft()
  let complete!: (value: Blob[]) => void
  mocks.images.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const pending = editor().previewImages()
  Object.assign(adminRoute, { query: 'id=draft-b' }); await flushPromises()
  complete([new Blob(['late-preview-a'], { type: 'image/png' })]); await pending
  expect(editor().data.title).toBe('笔记b')
  expect(editor().preview).toEqual([])
})
it('未关联选题时禁用保存并给出前置步骤', async () => {
  Object.assign(adminRoute, { tab: 'xhsMaterials', query: 'new=1' })
  wrapper = mount(XhsMaterials, { props: { user: { id: 7, username: 'review', role: 'admin', is_super_admin: true } }, global: { stubs } })
  await editor().w.readRoute(); await flushPromises()
  expect(wrapper.text()).toContain('选择关联选题库')
  expect(wrapper.find('[aria-label="资料名称"]').exists()).toBe(false)
  const save = wrapper.findAll('button').find(button => button.text() === '保存')!
  expect(save.attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('请先选择关联选题')
})

it('预览使用点击时的内容快照，同一笔记中修改配图也会丢弃迟到结果', async () => {
  await openDraft()
  let complete!: (value: Blob[]) => void
  mocks.images.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const pending = editor().previewImages()
  editor().data.cover_title = '编辑中的新封面'
  expect(mocks.images.mock.calls[0]?.[0].cover_title).toBe('封面a')
  complete([new Blob(['old-preview'], { type: 'image/png' })]); await pending
  expect(editor().preview).toEqual([])
})

it('旧预览结束不能解除新预览的加载状态', async () => {
  await openDraft()
  let oldComplete!: (value: Blob[]) => void, newComplete!: (value: Blob[]) => void
  mocks.images.mockImplementationOnce(() => new Promise(resolve => { oldComplete = resolve }))
  const oldPreview = editor().previewImages()
  editor().data.cover_title = '新封面'
  mocks.images.mockImplementationOnce(() => new Promise(resolve => { newComplete = resolve }))
  const newPreview = editor().previewImages()
  oldComplete([new Blob(['old'], { type: 'image/png' })]); await oldPreview
  expect((wrapper.vm as unknown as { previewing: boolean }).previewing).toBe(true)
  newComplete([new Blob(['new'], { type: 'image/png' })]); await newPreview
  expect(editor().preview[0]).toBe('data:image/png;base64,bmV3')
})

it('切换资料记录会回到出题设置', async () => {
  const read = mocks.request.getMockImplementation()!
  mocks.request.mockImplementation(async (path: string) => path.endsWith('material-two') ? { ...structuredClone(material), id: 'material-two', title: '第二份资料', data: { ...newMaterial(), title: '第二份资料' } } : read(path))
  Object.assign(adminRoute, { tab: 'xhsMaterials', query: 'id=material-one' })
  wrapper = mount(XhsMaterials, { props: { user: { id: 7, username: 'review', role: 'admin', is_super_admin: true } }, global: { stubs } })
  await editor().w.readRoute(); editor().step = 'review'
  Object.assign(adminRoute, { query: 'id=material-two' }); await flushPromises()
  expect(editor().data.title).toBe('第二份资料')
  expect(editor().step).toBe('setup')
})

it.each(['game_type', 'difficulty', 'question_count', 'questions'] as const)('资料修改 %s 后立即清除三项复核，保存前不能重新勾选', async field => {
  Object.assign(adminRoute, { tab: 'xhsMaterials', query: 'id=material-one' })
  wrapper = mount(XhsMaterials, { props: { user: { id: 7, username: 'review', role: 'admin', is_super_admin: true } }, global: { stubs } })
  await editor().w.readRoute()
  const data = (wrapper.vm as unknown as { data: ReturnType<typeof newMaterial> }).data
  Object.assign(data, { status: 'ready', accuracy_checked: true, scope_checked: true, layout_checked: true })
  if (field === 'game_type') data.game_type = 'quiz'
  if (field === 'difficulty') data.difficulty = 'hard'
  if (field === 'question_count') data.question_count = 20
  if (field === 'questions') data.questions[0]!.answer = '3'
  expect(data.status).toBe('draft')
  expect([data.accuracy_checked, data.scope_checked, data.layout_checked]).toEqual([false, false, false])
  editor().step = 'review'; await flushPromises()
  expect(wrapper.get('input[type="checkbox"]').attributes('disabled')).toBeDefined()
})

it('阶段入口打开列表，不恢复另一份旧笔记；当前阶段点击保留编辑页', async () => {
  navigateAdmin('xhsDrafts', { id: 'draft-b' })
  navigateAdmin('xhsMaterials', { id: 'material-one' })
  wrapper = mount(XhsContentNavigation, { props: { active: 'xhsMaterials', userId: 7 }, global: { stubs: { ...uiStubs, XhsTodayTasks: true, XhsGettingStarted: true } } })
  await wrapper.get('[title="打开资料制作列表"]').trigger('click')
  expect(adminRoute.query).toBe('id=material-one')
  await wrapper.get('[title="打开笔记制作列表"]').trigger('click')
  expect(adminRoute.tab).toBe('xhsDrafts')
  expect(adminRoute.query).toBe('')
})

it('已有笔记时下一步继续编辑，另建按钮才创建新笔记', async () => {
  const read = mocks.request.getMockImplementation()!
  const child = { id: 'draft-b', kind: 'drafts', title: '已有笔记', status: 'draft' }
  mocks.request.mockImplementation(async (path: string, options?: RequestInit) => path.endsWith('material-one') ?
    { ...structuredClone(material), revision: options?.method === 'PUT' ? 2 : 1, children: [child] } : read(path))
  Object.assign(adminRoute, { tab: 'xhsMaterials', query: 'id=material-one' })
  wrapper = mount(XhsMaterials, { props: { user: { id: 7, username: 'review', role: 'admin', is_super_admin: true } }, global: { stubs } })
  await editor().w.readRoute(); await flushPromises()
  await (wrapper.vm as unknown as { createDraft: (fresh?: boolean) => Promise<void> }).createDraft()
  expect(adminRoute.tab).toBe('xhsDrafts')
  expect(adminRoute.query).toBe('id=draft-b')
  Object.assign(adminRoute, { tab: 'xhsMaterials', query: 'id=material-one' }); await flushPromises()
  await (wrapper.vm as unknown as { createDraft: (fresh?: boolean) => Promise<void> }).createDraft(true)
  expect(new URLSearchParams(adminRoute.query).get('new')).toBe('1')
  expect(new URLSearchParams(adminRoute.query).get('parent')).toBe('material-one')
})

it('复制失败后下载点击时的文案，不混入后来切换的笔记内容', async () => {
  await openDraft()
  let fail!: (reason: Error) => void
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
  const pending = (wrapper.vm as unknown as { copyText: () => Promise<void> }).copyText()
  Object.assign(adminRoute, { query: 'id=draft-b' }); await flushPromises()
  fail(new Error('复制不可用')); await pending
  const blob = mocks.download.mock.calls[0]?.[0] as Blob
  expect(await blob.text()).toContain('正文a')
  expect(await blob.text()).not.toContain('正文b')
  expect(wrapper.text()).not.toContain('浏览器无法复制，已下载文案文件。')
})
