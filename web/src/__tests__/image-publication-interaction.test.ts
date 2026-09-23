import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ApiError, bindWorkspaceOwner, fetchScope } from '../api'
import { useAuthStore } from '../stores/auth'
import { useExamStore } from '../stores/exam'
import ImageWorkbench from '../components/ImageWorkbench.vue'
import ImagePublicationDialog from '../components/ImagePublicationDialog.vue'
import { addImagePublication, fetchPublicationCategories } from '../image-publication'
import { buildWorksheetPdf } from '../worksheet-pdf'
import { fetchImageOptions, generateWorksheetImage, fetchImageStatus, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'

vi.mock('../image-publication', async original => ({ ...await original<typeof import('../image-publication')>(), addImagePublication: vi.fn(), fetchPublicationCategories: vi.fn() }))
vi.mock('../worksheet-pdf', () => ({ buildWorksheetPdf: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), fetchScope: vi.fn().mockResolvedValue({ allowed: [], forbidden: [] }) }))
vi.mock('../image-generation', async original => ({ ...await original<typeof import('../image-generation')>(), fetchImageStatus: vi.fn(), generateWorksheetImage: vi.fn(), fetchImageOptions: vi.fn().mockResolvedValue({ configured: true }) }))

const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '加减法', difficulty: 'medium', items: [{ game_type: 'quiz', question_count: 4 }], style: 'clean', requirements: '' }
const images: WorksheetImage[] = ['first', 'second'].map(request_id => ({ request_id, b64_json: btoa('fixture'), mime_type: 'image/png', width: 2, height: 3, prompt: 'fixture' }))
const paper = { id: 'saved-paper', title: '加减法', status: 'draft', page_count: 2 }
const pdf = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
const input = defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('input', { value: props.modelValue, onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value) }) })
const stubs = {
  UModal: defineComponent({ props: ['open'], setup: (props, { slots }) => () => props.open ? h('div', { role: 'dialog' }, [slots.body?.(), slots.footer?.()]) : null }),
  UButton: defineComponent({ props: ['label', 'disabled', 'loading'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled || props.loading }, props.label || slots.default?.()) }),
  UInput: input, UTextarea: input, UInputNumber: input,
  USelect: defineComponent({ props: ['modelValue', 'items'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('select', { value: props.modelValue, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value) }, props.items.map((item: { value: string; label: string }) => h('option', { value: item.value }, item.label))) }),
  UFormField: defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  UAlert: defineComponent({ props: ['title', 'description'], setup: (props, { slots }) => () => h('div', [props.title, props.description, slots.actions?.()]) }), UIcon: true,
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  useAuthStore().user = { id: 17, role: 'admin', username: 'admin' }; bindWorkspaceOwner('17')
  vi.mocked(fetchImageOptions).mockResolvedValue({ configured: true } as Awaited<ReturnType<typeof fetchImageOptions>>)
  vi.mocked(fetchPublicationCategories).mockResolvedValue({ items: [{ id: 'visible', name: '练习', is_visible: true }, { id: 'hidden', name: '隐藏', is_visible: false }] })
  vi.mocked(addImagePublication).mockResolvedValue(paper)
  vi.mocked(buildWorksheetPdf).mockResolvedValue(pdf)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
})
afterEach(() => { wrapper?.unmount(); bindWorkspaceOwner(''); vi.unstubAllGlobals() })
async function dialog() {
  wrapper = mount(ImagePublicationDialog, { props: { open: true, images, params }, global: { stubs } })
  await flushPromises()
}
async function chooseCategory() { await wrapper.get('[aria-label="习题分类"]').setValue('visible') }

it('requires a visible category, uploads all pages once, and replaces save with a link to the created draft', async () => {
  await dialog()
  expect(wrapper.get('[aria-label="习题分类"]').text()).not.toContain('隐藏')
  await wrapper.get('form').trigger('submit'); expect(addImagePublication).not.toHaveBeenCalled()
  await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(buildWorksheetPdf).toHaveBeenCalledWith(images, expect.any(Function), expect.any(Function))
  expect(addImagePublication).toHaveBeenCalledWith(pdf, { title: '小学三年级数学·加减法', grade: params.grade, subject: params.subject, category_id: 'visible', description: '', keyword: params.keyword, question_types: params.items.map(item => item.game_type).join(','), question_count: params.items.reduce((sum, item) => sum + item.question_count, 0) * images.length })
  expect(wrapper.text()).toContain('已添加为后台习题草稿')
  expect(wrapper.get('[href="/admin/#papers?paper=saved-paper"]').text()).toBe('前往后台查看')
  expect(wrapper.find('form').exists()).toBe(false)
  expect(wrapper.emitted('saved')).toEqual([[paper]])
})

it('retains form data and the exact PDF for a manual retry after an unknown upload result', async () => {
  vi.mocked(addImagePublication).mockRejectedValueOnce(new ApiError('timeout', 0))
  await dialog(); await chooseCategory(); await wrapper.get('[aria-label="习题标题"]').setValue('我的练习')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('先到后台查看')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(buildWorksheetPdf).toHaveBeenCalledOnce()
  expect(addImagePublication).toHaveBeenCalledTimes(2)
  expect(vi.mocked(addImagePublication).mock.calls.every(([body, metadata]) => body === pdf && metadata.title === '我的练习')).toBe(true)
})

it('blocks double submission and cancels the upload when the account changes during PDF assembly', async () => {
  let finish!: (pdf: Blob) => void
  vi.mocked(buildWorksheetPdf).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await dialog(); await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  await wrapper.get('form').trigger('submit')
  expect(buildWorksheetPdf).toHaveBeenCalledOnce()
  useAuthStore().user = { id: 18, username: 'other', role: 'admin' }; bindWorkspaceOwner('18')
  finish(pdf); await flushPromises()
  expect(addImagePublication).not.toHaveBeenCalled()
})

async function workbench() {
  const store = useExamStore(); store.available = { '小学三年级': ['数学'] }
  localStorage.setItem('lc_u17_image_request', JSON.stringify({ version: 1, input: params, pages: [{ id: 'first', state: 'ready' }, { id: 'second', state: 'ready' }, { id: 'third', state: 'queued' }] }))
  vi.mocked(fetchImageStatus).mockImplementation(async id => ({ kind: 'image', status: 'succeeded', result: images.find(image => image.request_id === id)! } as Awaited<ReturnType<typeof fetchImageStatus>>))
  wrapper = mount(ImageWorkbench, { global: { stubs } })
  await flushPromises()
}
it('takes only completed pages and their original generation conditions even after editing the next request', async () => {
  await workbench()
  await wrapper.get('[aria-label="图片知识点"]').setValue('下次的新知识点')
  await wrapper.findAll('button').find(button => button.text() === '添加到后台')!.trigger('click')
  await flushPromises()
  const opened = wrapper.getComponent(ImagePublicationDialog)
  expect(opened.props('params')).toEqual(params)
  expect(opened.props('images').map(image => image.request_id)).toEqual(images.map(image => image.request_id))
  expect(opened.props('images').every(image => image.blob instanceof Blob && !image.b64_json)).toBe(true)
  await chooseCategory(); await wrapper.get('#image-publication').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('查看后台草稿')
})

it('does not expose backend publication or load categories for a regular teacher', async () => {
  useAuthStore().user!.role = 'user'
  await workbench()
  expect(wrapper.text()).not.toContain('添加到后台')
  expect(fetchPublicationCategories).not.toHaveBeenCalled()
})

it('keeps the configured worksheet when reselecting the current grade or subject', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学', '语文'] }
  store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加减法'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('.image-type-grid button').find(button => button.text() === '选择题')!.trigger('click')
  await wrapper.findAll('.image-grade-grid button').find(button => button.text() === '三年级')!.trigger('click')
  await wrapper.findAll('.image-choice-row button').find(button => button.text() === '数学')!.trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('加减法')
  expect(wrapper.get('.image-paper-exercise').text()).toContain('选择题')
  await wrapper.findAll('.image-choice-row button').find(button => button.text() === '语文')!.trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('')
  expect(wrapper.find('.image-paper-exercise').exists()).toBe(false)
})

it('updates the configuration preview without generating an image and enforces the five-type limit', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }
  store.grade = '小学三年级'; store.subject = '数学'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="图片知识点"]').setValue('乘法练习')
  expect(wrapper.get('.image-paper h4').text()).toBe('乘法练习')
  for (const button of wrapper.findAll('.image-type-grid button').slice(0, 5)) await button.trigger('click')
  expect(wrapper.findAll('.image-paper-exercise')).toHaveLength(5)
  expect(wrapper.findAll('.image-type-grid button').slice(5).every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.findAll('.image-style-grid button')[2]!.trigger('click')
  expect(wrapper.get('.image-paper').attributes('data-style')).toBe('black_white')
  expect(wrapper.get('.image-preview-disclaimer').text()).toContain('配置示意')
  expect(fetchImageStatus).not.toHaveBeenCalled()
})


it('filters curriculum knowledge points and toggles them without losing typed content', async () => {
  vi.mocked(fetchScope).mockResolvedValue({ allowed: ['加法', '减法'] })
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }
  store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '自定练习'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="搜索知识点"]').setValue('加')
  expect(wrapper.findAll('.image-knowledge-list button')).toHaveLength(1)
  await wrapper.get('.image-knowledge-list button').trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('自定练习、加法')
  await wrapper.get('.image-knowledge-list button').trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('自定练习')
  await wrapper.get('[aria-label="搜索知识点"]').setValue('不存在的知识点')
  expect(wrapper.get('.image-knowledge-list').text()).toContain('没有匹配项')
})

it('restores unsent configuration and saved publication links across remounts', async () => {
  await workbench()
  await wrapper.get('[aria-label="图片知识点"]').setValue('尚未生成的新练习')
  expect(JSON.parse(localStorage.getItem('lc_u17_image_request_draft')!).keyword).toBe('尚未生成的新练习')
  localStorage.setItem('lc_u17_image_request_published', JSON.stringify({ 'first,second': paper }))
  wrapper.unmount()
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('尚未生成的新练习')
  expect(wrapper.text()).toContain('查看后台草稿')
})

it('clears knowledge search on subject change and clamps counts to remaining capacity', async () => {
  const store = useExamStore(); store.available = { '小学三年级': ['数学', '语文'] }
  store.grade = '小学三年级'; store.subject = '数学'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('.image-type-grid button')[0]!.trigger('click')
  await wrapper.findAll('.image-type-grid button')[1]!.trigger('click')
  await wrapper.findAll('.image-count-row input')[0]!.setValue('20')
  await wrapper.findAll('.image-count-row input')[1]!.setValue('20')
  expect(wrapper.get('.image-order-summary').text()).toContain('24 题')
  expect(wrapper.findAll('.image-type-grid button').slice(2).every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.get('[aria-label="搜索知识点"]').setValue('数学')
  await wrapper.findAll('.image-choice-row button').find(button => button.text() === '语文')!.trigger('click')
  expect((wrapper.get('[aria-label="搜索知识点"]').element as HTMLInputElement).value).toBe('')
  await wrapper.findAll('.image-mobile-tabs button')[1]!.trigger('click')
  expect(wrapper.get('.image-workbench').attributes('data-mobile-panel')).toBe('preview')
})


it('keeps the manually selected preview when another page finishes', async () => {
  await workbench()
  let finish!: (image: WorksheetImage) => void
  vi.mocked(generateWorksheetImage).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await wrapper.findAll('button').find(button => button.text() === '继续生成剩余 1 张')!.trigger('click')
  await wrapper.findAll('.image-pages button')[0]!.trigger('click')
  finish({ ...images[0]!, request_id: 'third' }); await flushPromises()
  expect(wrapper.findAll('.image-pages button')[0]!.attributes('aria-pressed')).toBe('true')
  expect(wrapper.get('.worksheet-image').attributes('alt')).toContain('第 1 张')
})
