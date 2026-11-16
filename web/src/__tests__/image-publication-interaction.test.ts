import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ApiError, bindWorkspaceOwner, fetchScope } from '../api'
import { useAuthStore } from '../stores/auth'
import { useExamStore } from '../stores/exam'
import ImageWorkbench from '../components/ImageWorkbench.vue'
import ImagePublicationDialog from '../components/ImagePublicationDialog.vue'
import ImageCloudSaveDialog from '../components/ImageCloudSaveDialog.vue'
import CloudLibraryDialog from '../components/CloudLibraryDialog.vue'
import { addArchivePublication, addImagePublication, fetchPublicationCategories } from '../image-publication'
import { saveImageArchive } from '../image-cloud'
import { fetchArchive, fetchArchiveFolders, fetchArchives, fetchLibraryCapacity, type ArchiveDetail } from '../library'
import { buildWorksheetPdf } from '../worksheet-pdf'
import { buildWorksheetImagesZip } from '../worksheet-images'
import { downloadBlob } from '../../../shared/download'
import { fetchImageOptions, generateWorksheetImage, fetchImageStatus, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'

vi.mock('../image-publication', async original => ({ ...await original<typeof import('../image-publication')>(), addArchivePublication: vi.fn(), addImagePublication: vi.fn(), fetchPublicationCategories: vi.fn() }))
vi.mock('../image-cloud', async original => ({ ...await original<typeof import('../image-cloud')>(), saveImageArchive: vi.fn() }))
vi.mock('../library', async original => ({ ...await original<typeof import('../library')>(), fetchArchive: vi.fn(), fetchArchiveFolders: vi.fn(), fetchArchives: vi.fn(), fetchLibraryCapacity: vi.fn() }))
vi.mock('../worksheet-pdf', () => ({ buildWorksheetPdf: vi.fn() }))
vi.mock('../worksheet-images', () => ({ buildWorksheetImagesZip: vi.fn() }))
vi.mock('../../../shared/download', () => ({ downloadBlob: vi.fn(), triggerDownload: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), fetchScope: vi.fn().mockResolvedValue({ allowed: [], forbidden: [] }) }))
vi.mock('../image-generation', async original => ({ ...await original<typeof import('../image-generation')>(), previewImagePrompt: vi.fn(), fetchImageStatus: vi.fn(), generateWorksheetImage: vi.fn(), fetchImageOptions: vi.fn().mockResolvedValue({ configured: true }) }))

const params: ImageWorksheetParams = { grade: '小学三年级', subject: '数学', keyword: '加减法', difficulty: 'medium', items: [{ game_type: 'quiz', question_count: 4 }], style: 'clean', requirements: '' }
const images: WorksheetImage[] = ['first', 'second'].map(request_id => ({ request_id, b64_json: btoa('fixture'), mime_type: 'image/png', width: 2, height: 3, prompt: 'fixture' }))
const paper = { id: 'saved-paper', title: '加减法', status: 'draft', page_count: 2 }
const cloudArchive = { id: 'cloud-images', title: '加减法', grade: params.grade, subject: params.subject, file_status: 'ready', page_count: 2, question_count: 8, publication_id: null } as ArchiveDetail
const pdf = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
const zip = new Blob(['ZIP fixture'], { type: 'application/zip' })
const input = defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('input', { value: props.modelValue, onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value) }) })
const stubs = {
  UModal: defineComponent({ props: ['open'], setup: (props, { slots }) => () => props.open ? h('div', { role: 'dialog' }, [slots.body?.(), slots.footer?.()]) : null }),
  UButton: defineComponent({ props: ['label', 'disabled', 'loading'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled || props.loading }, props.label || slots.default?.()) }),
  UInput: input, UTextarea: input, UInputNumber: input,
  UCheckbox: defineComponent({ props: ['modelValue', 'label'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('input', { type: 'checkbox', checked: props.modelValue, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked) }) }),
  USelect: defineComponent({ props: ['modelValue', 'items'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('select', { value: props.modelValue, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value) }, props.items.map((item: { value: string; label: string }) => h('option', { value: item.value }, item.label))) }),
  UFormField: defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  UAlert: defineComponent({ props: ['title', 'description'], setup: (props, { slots }) => () => h('div', [props.title, props.description, slots.actions?.()]) }), UIcon: true, UBadge: true,
  UTooltip: defineComponent({ setup: (_, { slots }) => () => h('span', slots.default?.()) }), UDropdownMenu: true,
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  useAuthStore().user = { id: 17, role: 'admin', username: 'admin' }; bindWorkspaceOwner('17')
  vi.mocked(fetchImageOptions).mockResolvedValue({ configured: true } as Awaited<ReturnType<typeof fetchImageOptions>>)
  vi.mocked(fetchPublicationCategories).mockResolvedValue({ items: [{ id: 'visible', name: '练习', is_visible: true }, { id: 'hidden', name: '隐藏', is_visible: false }] })
  vi.mocked(addImagePublication).mockResolvedValue(paper)
  vi.mocked(addArchivePublication).mockResolvedValue(paper)
  vi.mocked(fetchArchiveFolders).mockResolvedValue({ items: [{ id: 'folder', name: '数学练习', paper_count: 0 }] })
  vi.mocked(fetchArchives).mockResolvedValue({ items: [{ ...cloudArchive }], total: 1, has_more: false })
  vi.mocked(fetchLibraryCapacity).mockResolvedValue({ storage_bytes: 1024, storage_limit_bytes: 5 * 1024 ** 3 })
  vi.mocked(fetchArchive).mockResolvedValue({ ...cloudArchive, assets: [{ id: 'pdf', kind: 'pdf', page_number: 0, byte_size: 12, url: '/api/v1/library/assets/pdf' }] })
  vi.mocked(saveImageArchive).mockResolvedValue(cloudArchive)
  vi.mocked(buildWorksheetPdf).mockResolvedValue(pdf)
  vi.mocked(buildWorksheetImagesZip).mockResolvedValue(zip)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
})
afterEach(() => { wrapper?.unmount(); bindWorkspaceOwner(''); vi.unstubAllGlobals() })
async function dialog(inputParams = params) {
  wrapper = mount(ImagePublicationDialog, { props: { open: true, images, params: inputParams }, global: { stubs } })
  await flushPromises()
}
async function chooseCategory() { await wrapper.get('[aria-label="习题分类"]').setValue('visible') }

it('requires a visible category, uploads all pages once, and replaces save with a link to the created draft', async () => {
  await dialog()
  expect(wrapper.get('[aria-label="习题分类"]').text()).not.toContain('隐藏')
  await wrapper.get('form').trigger('submit'); expect(addImagePublication).not.toHaveBeenCalled()
  await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(buildWorksheetPdf).toHaveBeenCalledWith(images, expect.any(Function), expect.any(Function))
  expect(addImagePublication).toHaveBeenCalledWith(pdf, { title: '小学三年级数学·加减法', grade: params.grade, subject: params.subject, category_id: 'visible', description: '', keyword: params.keyword, question_types: params.items.map(item => item.game_type).join(','), question_count: 8 })
  expect(wrapper.text()).toContain('已添加为后台习题草稿')
  expect(wrapper.get('[href="/admin/#papers?paper=saved-paper"]').text()).toBe('前往后台查看')
  expect(wrapper.find('form').exists()).toBe(false)
  expect(wrapper.emitted('saved')).toEqual([[paper]])
})

it.each([
  [{ game_type: 'quiz' }],
  [{ game_type: 'quiz', question_count: null }],
  [{ game_type: 'quiz', question_count: 4 }, { game_type: 'fill_blank', question_count: null }],
])('omits the publication count when any quantity is automatic: %j', async (...items) => {
  await dialog({ ...params, items })
  await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(addImagePublication).toHaveBeenCalledOnce()
  const metadata = vi.mocked(addImagePublication).mock.calls[0]![1]
  expect(metadata).not.toHaveProperty('question_count')
  expect(metadata.question_types).toBe(items.map(item => item.game_type).join(','))
})

it('publishes automatic worksheets without inventing topics, types or a count', async () => {
  await dialog({ ...params, keyword: '', items: [] })
  await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(addImagePublication).toHaveBeenCalledWith(pdf, {
    title: '小学三年级数学·年级知识练习', grade: params.grade, subject: params.subject,
    category_id: 'visible', description: '', keyword: '', question_types: '',
  })
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
it('uses the server concurrency allowance, remembers the choice and clamps it after a server limit change', async () => {
  vi.mocked(fetchImageOptions).mockResolvedValue({ configured: true, max_concurrency: 4, default_concurrency: 2 })
  await workbench()
  expect((wrapper.get('[aria-label="同时生成图片数"]').element as HTMLSelectElement).value).toBe('2')
  expect(wrapper.findAll('[aria-label="同时生成图片数"] option')).toHaveLength(4)
  await wrapper.get('[aria-label="同时生成图片数"]').setValue('3')
  expect(localStorage.getItem('lc_u17_image_request_concurrency')).toBe('3')
  wrapper.unmount(); await workbench()
  expect((wrapper.get('[aria-label="同时生成图片数"]').element as HTMLSelectElement).value).toBe('3')
  vi.mocked(fetchImageOptions).mockResolvedValue({ configured: true, max_concurrency: 1, default_concurrency: 1 })
  wrapper.unmount(); await workbench()
  expect((wrapper.get('[aria-label="同时生成图片数"]').element as HTMLSelectElement).value).toBe('1')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})
it('takes only completed pages and their original generation conditions even after editing the next request', async () => {
  await workbench()
  await wrapper.get('[aria-label="图片知识点"]').setValue('下次的新知识点')
  await wrapper.findAll('button').find(button => button.text() === '添加到后台')!.trigger('click')
  await flushPromises()
  const opened = wrapper.getComponent(ImagePublicationDialog)
  expect(opened.props('params')).toEqual(params)
  expect(opened.props('images')!.map(image => image.request_id)).toEqual(images.map(image => image.request_id))
  expect(opened.props('images')!.every(image => image.blob instanceof Blob && !image.b64_json)).toBe(true)
  await chooseCategory(); await wrapper.get('#image-publication').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('查看后台草稿')
})

it('uses the same chosen range for original PNGs, cloud archives and publication, with a distinct saved state per range', async () => {
  await workbench()
  await wrapper.get('[aria-label="范围起始张数"]').setValue('2')
  await wrapper.get('[aria-label="范围结束张数"]').setValue('3')
  await wrapper.findAll('button').find(button => button.text() === '批量下载图片（1 张）')!.trigger('click')
  await vi.waitFor(() => expect(buildWorksheetImagesZip).toHaveBeenCalledOnce())
  expect(vi.mocked(buildWorksheetImagesZip).mock.calls[0][0].map(image => image?.request_id || null)).toEqual([null, 'second', null])
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '保存到云端')!.trigger('click')
  await flushPromises()
  const cloud = wrapper.getComponent(ImageCloudSaveDialog)
  expect(cloud.props('images').map(image => image.request_id)).toEqual(['second'])
  cloud.vm.$emit('close'); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '添加到后台')!.trigger('click')
  await flushPromises()
  const publication = wrapper.getComponent(ImagePublicationDialog)
  expect(publication.props('images')!.map(image => image.request_id)).toEqual(['second'])
  publication.vm.$emit('close'); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '全部图片')!.trigger('click')
  await wrapper.findAll('button').find(button => button.text() === '保存到云端')!.trigger('click')
  await flushPromises()
  expect(wrapper.getComponent(ImageCloudSaveDialog).props('images').map(image => image.request_id)).toEqual(['first', 'second'])
})

it('does not expose backend publication or load categories for a regular teacher', async () => {
  useAuthStore().user!.role = 'user'
  await workbench()
  expect(wrapper.text()).not.toContain('添加到后台')
  expect(fetchPublicationCategories).not.toHaveBeenCalled()
})

it('saves completed images to the cloud using original batch conditions for a regular teacher', async () => {
  useAuthStore().user!.role = 'user'
  await workbench()
  await wrapper.get('[aria-label="图片知识点"]').setValue('下一批条件')
  await wrapper.findAll('button').find(button => button.text() === '保存到云端')!.trigger('click'); await flushPromises()
  const opened = wrapper.getComponent(ImageCloudSaveDialog)
  expect(opened.props('params')).toEqual(params)
  expect(opened.props('images').map(image => image.request_id)).toEqual(['first', 'second'])
  await opened.get('[aria-label="云端图片标题"]').setValue('云端加减练习')
  await opened.get('[aria-label="图片云端文件夹"]').setValue('folder')
  await opened.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(opened.text()).toContain('已保存到云端'))
  expect(saveImageArchive).toHaveBeenCalledWith(pdf, expect.stringMatching(/^[a-f0-9]{64}$/), '云端加减练习', params, 2, 'folder', expect.any(AbortSignal))
  expect(opened.text()).toContain('已保存到云端')
  expect(addImagePublication).not.toHaveBeenCalled()
  expect(addArchivePublication).not.toHaveBeenCalled()
  expect(generateWorksheetImage).not.toHaveBeenCalled()
  await opened.findAll('button').find(button => button.text() === '查看云端试卷')!.trigger('click')
  expect(wrapper.emitted('library')).toHaveLength(1)
})

it('reuses the exact PDF and stable request key after an unknown cloud upload result', async () => {
  vi.mocked(saveImageArchive).mockRejectedValueOnce(new ApiError('timeout', 0))
  wrapper = mount(ImageCloudSaveDialog, { props: { open: true, images, params }, global: { stubs } }); await flushPromises()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(wrapper.text()).toContain('同一批图片不会重复归档'))
  await wrapper.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(saveImageArchive).toHaveBeenCalledTimes(2))
  expect(buildWorksheetPdf).toHaveBeenCalledOnce()
  expect(saveImageArchive).toHaveBeenCalledTimes(2)
  expect(vi.mocked(saveImageArchive).mock.calls[0]!.slice(0, 6)).toEqual(vi.mocked(saveImageArchive).mock.calls[1]!.slice(0, 6))
})

it('cancels cloud upload when the account changes while preparing the PDF', async () => {
  let finish!: (blob: Blob) => void
  vi.mocked(buildWorksheetPdf).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  wrapper = mount(ImageCloudSaveDialog, { props: { open: true, images, params }, global: { stubs } }); await flushPromises()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(buildWorksheetPdf).toHaveBeenCalledOnce())
  await wrapper.get('form').trigger('submit')
  expect(buildWorksheetPdf).toHaveBeenCalledOnce()
  bindWorkspaceOwner('18')
  finish(pdf); await flushPromises()
  expect(saveImageArchive).not.toHaveBeenCalled()
})

it('prepares a mini-program draft directly from a cloud archive without generating or uploading files', async () => {
  wrapper = mount(CloudLibraryDialog, { props: { open: true }, global: { stubs } }); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '准备发布到小程序')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('使用已保存的云端文件')
  await chooseCategory(); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(addArchivePublication).toHaveBeenCalledExactlyOnceWith('cloud-images', { title: cloudArchive.title, category_id: 'visible', description: '' })
  expect(buildWorksheetPdf).not.toHaveBeenCalled()
  expect(saveImageArchive).not.toHaveBeenCalled()
  expect(addImagePublication).not.toHaveBeenCalled()
  expect(wrapper.find('[href="/admin/#papers?paper=saved-paper"]').exists()).toBe(true)
})

it('shows an existing publication link after reloading cloud records and hides publication from regular teachers', async () => {
  vi.mocked(fetchArchives).mockResolvedValue({ items: [{ ...cloudArchive, publication_id: paper.id }], total: 1, has_more: false })
  wrapper = mount(CloudLibraryDialog, { props: { open: true }, global: { stubs } }); await flushPromises()
  expect(wrapper.text()).toContain('查看小程序发布')
  expect(wrapper.text()).not.toContain('准备发布到小程序')
  useAuthStore().user!.role = 'user'; await flushPromises()
  expect(wrapper.text()).not.toContain('查看小程序发布')
  expect(fetchPublicationCategories).not.toHaveBeenCalled()
})

it('does not download a cloud file after an account switch or save an unexpected error page as PDF', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response('error page', { headers: { 'Content-Type': 'text/html' } }))
    .mockImplementationOnce(async () => { bindWorkspaceOwner('18'); return new Response(pdf) })
  vi.stubGlobal('fetch', fetch)
  wrapper = mount(CloudLibraryDialog, { props: { open: true }, global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="下载归档 PDF"]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('下载文件无效')
  expect(downloadBlob).not.toHaveBeenCalled()
  await wrapper.get('[aria-label="下载归档 PDF"]').trigger('click'); await flushPromises()
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(downloadBlob).not.toHaveBeenCalled()
})

it('downloads every completed image in the batch as one ZIP even when another page is selected', async () => {
  useAuthStore().user!.role = 'user'
  await workbench()
  await wrapper.get('[aria-label="第 3 张 · 待生成"]').trigger('click')
  await wrapper.findAll('button').find(button => button.text() === '批量下载图片（2 张）')!.trigger('click')
  await flushPromises()
  const pages = vi.mocked(buildWorksheetImagesZip).mock.calls[0]![0]
  expect(pages.map(image => image?.request_id ?? null)).toEqual(['first', 'second', null])
  expect(downloadBlob).toHaveBeenCalledExactlyOnceWith(zip, '习题图片-first-2张.zip')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it('keeps images available and allows retry when ZIP creation fails', async () => {
  vi.mocked(buildWorksheetImagesZip).mockRejectedValueOnce(new Error('打包失败，请重试'))
  await workbench()
  const button = () => wrapper.findAll('button').find(button => button.text() === '批量下载图片（2 张）')!
  await button().trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('打包失败，请重试')
  expect(downloadBlob).not.toHaveBeenCalled()
  expect(wrapper.findAll('.image-pages img')).toHaveLength(2)
  expect(button().attributes('disabled')).toBeUndefined()
  await button().trigger('click'); await flushPromises()
  expect(downloadBlob).toHaveBeenCalledOnce()
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it.each(['account', 'unmount'])('blocks conflicting batch actions and does not download after %s changes', async change => {
  let finish!: (blob: Blob) => void
  vi.mocked(buildWorksheetImagesZip).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await workbench()
  const button = () => wrapper.findAll('button').find(button => button.text() === '批量下载图片（2 张）')!
  await button().trigger('click'); await flushPromises()
  expect(button().attributes('disabled')).toBeDefined()
  for (const label of ['下载 PDF（2 页）', '继续生成剩余 1 张', '历史批次', '添加到后台']) {
    expect(wrapper.findAll('button').find(button => button.text() === label)!.attributes('disabled')).toBeDefined()
  }
  await wrapper.get('form').trigger('submit')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
  expect(buildWorksheetImagesZip).toHaveBeenCalledOnce()
  if (change === 'account') {
    useAuthStore().user = { id: 18, username: 'other', role: 'admin' }; bindWorkspaceOwner('18')
  } else wrapper.unmount()
  finish(zip); await flushPromises()
  expect(downloadBlob).not.toHaveBeenCalled()
})

it('keeps the configured worksheet when reselecting the current grade or subject', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学', '语文'] }
  store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加减法'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('.image-type-grid button').find(button => button.text() === '选择题')!.trigger('click')
  await wrapper.get('[aria-label="图片年级"]').setValue('小学三年级')
  await wrapper.get('[aria-label="图片科目"]').setValue('数学')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('加减法')
  expect(wrapper.get('.image-paper-exercise').text()).toContain('选择题')
  await wrapper.get('[aria-label="图片科目"]').setValue('语文')
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
  vi.mocked(fetchScope).mockResolvedValue({ allowed: ['旧知识点'], books: [{
    id: 'test-book', semester: '上册', series: '人教版数学', source_url: 'https://jc.pep.com.cn/',
    verified_on: '2026-10-10', units: [{ title: '加法', page: 1, topics: [] }, { title: '减法', page: 2, topics: [] }],
  }] })
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }
  store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '自定练习'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="搜索知识点"]').setValue('加')
  expect(wrapper.findAll('.image-knowledge-list button')).toHaveLength(1)
  await wrapper.get('.image-knowledge-list button').trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('自定练习、上册·加法')
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
  await wrapper.get('[aria-label="填空题指定题量"]').setValue(true)
  await wrapper.get('[aria-label="填空题题量"]').setValue('20')
  await wrapper.get('[aria-label="判断题指定题量"]').setValue(true)
  await wrapper.get('[aria-label="判断题题量"]').setValue('20')
  expect(wrapper.get('.image-order-summary').text()).toContain('24 题')
  expect(wrapper.findAll('.image-type-grid button').slice(2).every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.get('[aria-label="搜索知识点"]').setValue('数学')
  await wrapper.get('[aria-label="图片科目"]').setValue('语文')
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

it('applies a quick arrangement without generating and allows custom counts afterward', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }; store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加法'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('.image-arrangements button')[0]!.trigger('click')
  expect(wrapper.get('.image-order-summary').text()).toBe('1 张 · 题量自动安排')
  expect(wrapper.findAll('.image-paper-exercise')).toHaveLength(2)
  expect(wrapper.findAll('.image-count-value')).toHaveLength(0)
  await wrapper.get('[aria-label="选择题指定题量"]').setValue(true)
  await wrapper.get('[aria-label="选择题题量"]').setValue('6')
  expect(wrapper.get('.image-order-summary').text()).toBe('1 张 · 已指定 6 题，其余自动')
  expect(wrapper.findAll('.image-arrangements button').every(button => button.attributes('aria-pressed') === 'false')).toBe(true)
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it('uses subject-appropriate types in the comprehensive arrangement', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学', '语文'] }; store.grade = '小学三年级'; store.subject = '数学'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('.image-arrangements button')[1]!.trigger('click')
  expect(wrapper.get('.image-custom summary').text()).toContain('判断题')
  await wrapper.get('[aria-label="图片科目"]').setValue('语文')
  await wrapper.findAll('.image-arrangements button')[1]!.trigger('click')
  expect(wrapper.get('.image-custom summary').text()).toContain('连线配对')
  expect(wrapper.get('.image-custom summary').text()).not.toContain('判断题')
  expect(wrapper.get('.image-order-summary').text()).toContain('题量自动安排')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it('defaults each newly selected type to automatic and persists optional quantities', async () => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }; store.grade = '小学三年级'; store.subject = '数学'; store.keyword = '加法'
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  const selectType = () => wrapper.findAll('.image-type-grid button').find(button => button.text() === '选择题')!
  await selectType().trigger('click')
  expect(wrapper.find('[aria-label="选择题题量"]').exists()).toBe(false)
  expect(wrapper.get('.image-paper-exercise small').text()).toBe('自动安排')
  expect(JSON.parse(localStorage.getItem('lc_u17_image_request_draft')!).items).toEqual([{ game_type: 'quiz', question_count: null }])
  await wrapper.get('[aria-label="选择题指定题量"]').setValue(true)
  await wrapper.get('[aria-label="选择题题量"]').setValue('6')
  expect(wrapper.get('.image-order-summary').text()).toBe('1 张 × 6 题')
  await wrapper.get('[aria-label="选择题指定题量"]').setValue(false)
  expect(wrapper.find('[aria-label="选择题题量"]').exists()).toBe(false)
  await wrapper.get('[aria-label="选择题指定题量"]').setValue(true)
  await wrapper.get('[aria-label="选择题题量"]').setValue('')
  expect(wrapper.get('.image-order-summary').text()).toContain('题量自动安排')
  await wrapper.get('[aria-label="选择题指定题量"]').setValue(true)
  await selectType().trigger('click'); await selectType().trigger('click')
  expect(wrapper.find('[aria-label="选择题题量"]').exists()).toBe(false)
  wrapper.unmount(); wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  expect(wrapper.get('.image-order-summary').text()).toBe('1 张 · 题量自动安排')
  expect(wrapper.get('.image-paper-exercise small').text()).toBe('自动安排')
})

it('requires grade and subject but generates with empty topics and types, restoring automatic drafts', async () => {
  const store = useExamStore()
  store.available = { '小学一年级': ['数学'] }
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.get('form').trigger('submit')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
  await wrapper.get('[aria-label="图片年级"]').setValue('小学一年级')
  await wrapper.get('form').trigger('submit')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
  await wrapper.get('[aria-label="图片科目"]').setValue('数学')
  expect(wrapper.get('.image-order-summary').text()).toBe('1 张 · 题型、题量自动安排')
  await wrapper.findAll('.image-type-grid button')[0]!.trigger('click')
  await wrapper.findAll('button').find(button => button.text() === '恢复自动题型')!.trigger('click')
  expect(wrapper.findAll('.image-paper-exercise')).toHaveLength(0)
  wrapper.unmount(); wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  expect((wrapper.get('[aria-label="图片科目"]').element as HTMLSelectElement).value).toBe('数学')
  expect(wrapper.get('.image-order-summary').text()).toContain('题型、题量自动安排')
  vi.mocked(generateWorksheetImage).mockResolvedValue(images[0]!)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(generateWorksheetImage).toHaveBeenCalledWith(expect.objectContaining({
    grade: '小学一年级', subject: '数学', keyword: '', items: [],
  }), expect.any(String))
  expect(wrapper.get('.image-batch-title h3').text()).toBe('小学一年级数学·年级知识练习')
})

it.each([undefined, null, 7])('restores old and optional quantity drafts without changing their intent: %s', async count => {
  localStorage.setItem('lc_u17_image_request_draft', JSON.stringify({ ...params, items: [{ game_type: 'quiz', question_count: count }] }))
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  if (count == null) {
    expect(wrapper.find('[aria-label="选择题题量"]').exists()).toBe(false)
    expect(wrapper.get('.image-order-summary').text()).toBe('1 张 · 题量自动安排')
  } else {
    expect((wrapper.get('[aria-label="选择题题量"]').element as HTMLInputElement).value).toBe('7')
    expect(wrapper.get('.image-order-summary').text()).toBe('1 张 × 7 题')
  }
})

it('keeps original batch conditions visible and reuses them without submitting a new batch', async () => {
  await workbench()
  await wrapper.get('[aria-label="图片知识点"]').setValue('新知识点')
  expect(wrapper.get('.image-batch-title').text()).toContain('加减法')
  expect(wrapper.get('.image-generate-actions').text()).toContain('设置已调整')
  await wrapper.findAll('button').find(button => button.text() === '复用设置')!.trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('加减法')
  expect(wrapper.get('.image-workbench').attributes('data-mobile-panel')).toBe('settings')
  expect(wrapper.get('.image-generate-actions').text()).not.toContain('设置已调整')
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it('confirms clearing all image inputs, persists the empty draft and retains results and publication links', async () => {
  await workbench()
  localStorage.setItem('lc_u17_image_request_published', JSON.stringify({ 'first,second': paper }))
  await wrapper.get('[aria-label="补充要求"]').setValue('额外要求')
  await wrapper.get('[aria-label="图片难度"]').setValue('hard')
  const clear = () => wrapper.findAll('button').find(button => button.text() === '清空设置')!
  const confirm = vi.fn(() => false)
  vi.stubGlobal('confirm', confirm)
  await clear().trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('加减法')
  confirm.mockReturnValue(true)
  await clear().trigger('click')
  await flushPromises()
  const expected = { grade: '', subject: '', keyword: '', difficulty: 'medium', items: [], requirements: '', image_count: 1, style: 'clean' }
  expect(JSON.parse(localStorage.getItem('lc_u17_image_request_draft')!)).toMatchObject(expected)
  expect(wrapper.get('.image-workbench').attributes('data-mobile-panel')).toBe('settings')
  expect(wrapper.get('.image-batch-title h3').text()).toBe('加减法')
  expect(wrapper.findAll('.image-pages button')).toHaveLength(3)
  expect(clear().attributes('disabled')).toBeDefined()
  expect(generateWorksheetImage).not.toHaveBeenCalled()
  wrapper.unmount()
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  expect((wrapper.get('[aria-label="图片年级"]').element as HTMLSelectElement).value).toBe('')
  expect(wrapper.findAll('.image-count-row')).toHaveLength(0)
  expect(wrapper.text()).toContain('查看后台草稿')
  expect(wrapper.get('.image-batch-title h3').text()).toBe('加减法')
  await wrapper.findAll('button').find(button => button.text() === '复用设置')!.trigger('click')
  expect((wrapper.get('[aria-label="图片知识点"]').element as HTMLInputElement).value).toBe('加减法')
  expect(wrapper.get('.image-order-summary').text()).toBe('3 张 × 4 题')
})

it.each(['success', 'failure'])('does not restore stale scope or prompt state after clearing: %s', async outcome => {
  const store = useExamStore()
  store.available = { '小学三年级': ['数学'] }; store.grade = '小学三年级'; store.subject = '数学'
  let finishScope!: (value: { allowed: string[] }) => void
  let finishPrompt!: (value: { prompt: string }) => void, failPrompt!: (reason: Error) => void
  vi.mocked(fetchScope).mockImplementationOnce(() => new Promise(resolve => { finishScope = resolve }))
  vi.mocked(previewImagePrompt).mockImplementationOnce(() => new Promise((resolve, reject) => { finishPrompt = resolve; failPrompt = reject }))
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '查看生成说明')!.trigger('click')
  vi.stubGlobal('confirm', vi.fn(() => true))
  await wrapper.findAll('button').find(button => button.text() === '清空设置')!.trigger('click')
  finishScope({ allowed: ['旧知识点'] })
  if (outcome === 'success') finishPrompt({ prompt: '过期的出题说明' })
  else failPrompt(new Error('过期请求失败'))
  await flushPromises()
  expect(wrapper.text()).not.toContain('旧知识点')
  expect(wrapper.text()).not.toContain('过期')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})

it('disables clearing during generation, uncertain recovery, publication and account changes', async () => {
  await workbench()
  const clear = () => wrapper.findAll('button').find(button => button.text() === '清空设置')!
  await wrapper.findAll('button').find(button => button.text() === '添加到后台')!.trigger('click')
  await flushPromises()
  expect(clear().attributes('disabled')).toBeDefined()
  wrapper.getComponent(ImagePublicationDialog).vm.$emit('close'); await flushPromises()
  expect(clear().attributes('disabled')).toBeUndefined()
  let fail!: (reason: Error) => void
  vi.mocked(generateWorksheetImage).mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
  await wrapper.findAll('button').find(button => button.text() === '继续生成剩余 1 张')!.trigger('click')
  await flushPromises()
  expect(clear().attributes('disabled')).toBeDefined()
  fail(new ApiError('响应中断', 504)); await flushPromises()
  expect(wrapper.get('.image-batch-status').text()).toContain('生成结果待确认')
  expect(clear().attributes('disabled')).toBeDefined()
  useExamStore().accountChanged = true; await flushPromises()
  expect(clear().attributes('disabled')).toBeDefined()
})

it('restores to results and keeps recovery actions with the preview after an uncertain response', async () => {
  await workbench()
  expect(wrapper.get('.image-workbench').attributes('data-mobile-panel')).toBe('preview')
  vi.mocked(generateWorksheetImage).mockRejectedValueOnce(new ApiError('响应中断', 504))
  await wrapper.findAll('button').find(button => button.text() === '继续生成剩余 1 张')!.trigger('click')
  await flushPromises()
  expect(wrapper.get('.image-batch-status').text()).toContain('生成结果待确认')
  expect(wrapper.findAll('.image-batch-actions button').map(button => button.text())).toContain('查询本次结果')
  expect(wrapper.findAll('.image-batch-actions button').some(button => button.text().startsWith('继续生成'))).toBe(false)
  vi.mocked(fetchImageStatus).mockResolvedValue({ kind: 'image', status: 'succeeded', result: { ...images[0]!, request_id: 'third' } } as Awaited<ReturnType<typeof fetchImageStatus>>)
  await wrapper.findAll('.image-batch-actions button').find(button => button.text() === '查询本次结果')!.trigger('click')
  await flushPromises()
  expect(wrapper.get('.image-batch-status').text()).toContain('本批图片已全部完成')
  expect(generateWorksheetImage).toHaveBeenCalledOnce()
})

it('keeps the result screen usable when a saved batch has malformed conditions', async () => {
  localStorage.setItem('lc_u17_image_request', JSON.stringify({ version: 1, input: { ...params, items: [null] }, pages: [{ id: 'queued-bad-draft', state: 'queued' }] }))
  wrapper = mount(ImageWorkbench, { global: { stubs } }); await flushPromises()
  expect(wrapper.get('.image-batch-status').text()).toContain('原批次设置无法读取')
  expect(wrapper.findAll('button').find(button => button.text() === '继续生成剩余 1 张')!.attributes('disabled')).toBeDefined()
  expect(generateWorksheetImage).not.toHaveBeenCalled()
})
