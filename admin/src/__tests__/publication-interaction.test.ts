import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import PublicPapers from '../components/PublicPapers.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { readAdminRoute } from '../navigation'
import * as catalog from '../catalog'
const mocks = vi.hoisted(() => ({ categories: vi.fn(), dictionary: vi.fn() }))
vi.mock('../site', () => ({ siteCategories: mocks.categories, siteDictionary: mocks.dictionary }))
vi.mock('../catalog', async original => ({ ...await original<typeof import('../catalog')>(),
  catalogList: vi.fn().mockResolvedValue({ items: [], total: 0 }), catalogStats: vi.fn().mockResolvedValue({}),
  catalogSources: vi.fn().mockResolvedValue({ items: [], has_more: false }),
  createPublication: vi.fn(), updatePublication: vi.fn(), catalogDetail: vi.fn() }))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(catalog.catalogList).mockResolvedValue({ items: [], total: 0, has_more: false })
  history.replaceState(null, '', '/admin/#papers'); readAdminRoute()
  mocks.categories.mockReset(); mocks.dictionary.mockReset()
  mocks.categories.mockResolvedValue({ items: [{ id: 'category', name: '练习', is_visible: true }] })
  mocks.dictionary.mockResolvedValue({ items: [{ value: 'available', label: '可用选项' }] })
})

it('required option failures show independent retry actions and retain typed form content', async () => {
  mocks.categories.mockRejectedValueOnce(new Error('offline'))
  mocks.dictionary.mockRejectedValueOnce(new Error('offline'))
  const wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(PublicPapers, { user: { id: 1, username: 'admin', role: 'admin' } })) }), {
    global: { stubs: { ...uiStubs,
      UAlert: defineComponent({ props: ['title'], setup: (props, { slots }) => () => h('div', [props.title, slots.actions?.()]) }),
      CatalogBatchDialog: true, CatalogRevisionDialog: true, PaperMetadataDialog: true, PaperEditionDialog: true, UTextarea: true } },
  })
  const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
  try {
    await flushPromises(); await button('添加习题').trigger('click'); await flushPromises()
    const title = wrapper.find('input[maxlength="240"]')
    await title.setValue('保留已填写的试卷标题')
    await button('手动导入 PDF').trigger('click')
    expect(wrapper.text()).toContain('分类加载失败')
    expect(wrapper.text()).toContain('年级与科目加载失败')
    await button('重试加载分类').trigger('click'); await flushPromises()
    await button('重试加载年级与科目').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('分类加载失败')
    expect(wrapper.text()).not.toContain('年级与科目加载失败')
    await button('选择工作台习题').trigger('click')
    expect((wrapper.get('input[maxlength="240"]').element as HTMLInputElement).value).toBe('保留已填写的试卷标题')
  } finally { wrapper.unmount() }
})

const paper = { id: 'paper', title: '旧标题', revision: 1, description: '', category_id: 'category', status: 'draft', featured: false,
  view_access: 'free', download_access: 'free', assets: [], file_status: 'ready' } as unknown as catalog.CatalogDetail
function mountPapers() {
  return mount(defineComponent({ setup: () => () => h(KeepAlive, () => h(PublicPapers, { user: { id: 1, username: 'admin', role: 'admin' } })) }), {
    global: { stubs: { ...uiStubs, CatalogBatchDialog: true, CatalogRevisionDialog: true, PaperMetadataDialog: true, PaperEditionDialog: true, UTextarea: true } },
  })
}
it('不选原稿即可创建网盘习题，链接无效时阻止提交', async () => {
  vi.mocked(catalog.createPublication).mockResolvedValue({ ...paper, download_mode: 'external' })
  const wrapper = mountPapers()
  const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
  try {
    await flushPromises(); await button('添加习题').trigger('click'); await flushPromises()
    await button('仅添加网盘链接').trigger('click')
    await wrapper.get('input[maxlength="240"]').setValue('网盘资料')
    await wrapper.get('[aria-label="网盘习题年级"]').setValue('available')
    await wrapper.get('[aria-label="网盘习题科目"]').setValue('available')
    await wrapper.get('[aria-label="网盘链接"]').setValue('javascript:alert(1)')
    await wrapper.get('#publication-form').trigger('submit')
    expect(catalog.createPublication).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请填写完整的')
    await wrapper.get('[aria-label="网盘链接"]').setValue(' https://pan.example.com/s/a?from=school ')
    await wrapper.get('[aria-label="提取码"]').setValue(' Ab12 ')
    await wrapper.get('#publication-form').trigger('submit'); await flushPromises()
    expect(vi.mocked(catalog.createPublication).mock.lastCall?.[1]).toMatchObject({
      paper_id: '', title: '网盘资料', grade: 'available', subject: 'available', download_mode: 'external',
      external_url: 'https://pan.example.com/s/a?from=school', external_code: 'Ab12',
    })
  } finally { wrapper.unmount() }
})
it('编辑网盘资料保留链接，切换 PDF 后不再提交旧链接和提取码', async () => {
  const external = { ...paper, download_mode: 'external' as const, external_url: 'https://pan.example.com/a', external_code: 'A123' }
  vi.mocked(catalog.catalogList).mockResolvedValue({ items: [external], total: 1, has_more: false })
  vi.mocked(catalog.updatePublication).mockResolvedValue({ ...paper, revision: 2 })
  const wrapper = mountPapers()
  try {
    await flushPromises(); await wrapper.get('[aria-label="编辑 旧标题"]').trigger('click')
    expect((wrapper.get('[aria-label="网盘链接"]').element as HTMLInputElement).value).toBe(external.external_url)
    await wrapper.get('[aria-label="下载方式"]').setValue('pdf')
    await wrapper.get('#publication-form').trigger('submit'); await flushPromises()
    expect(vi.mocked(catalog.updatePublication).mock.lastCall?.[2]).toMatchObject({ download_mode: 'pdf', external_url: '', external_code: '' })
  } finally { wrapper.unmount() }
})
it('编辑可修改标题，保存后刷新列表和版本号，继续保存不会复用旧版本', async () => {
  vi.mocked(catalog.catalogList).mockResolvedValue({ items: [paper], total: 1, has_more: false })
  vi.mocked(catalog.updatePublication).mockResolvedValueOnce({ ...paper, title: '新标题', revision: 2 }).mockResolvedValueOnce({ ...paper, title: '再次修改', revision: 3 })
  const wrapper = mountPapers()
  try {
    await flushPromises(); await wrapper.get('[aria-label="编辑 旧标题"]').trigger('click')
    await wrapper.get('input[maxlength="240"]').setValue('新标题')
    await wrapper.get('#publication-form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('公共习题已更新')
    await wrapper.get('input[maxlength="240"]').setValue('再次修改')
    await wrapper.get('#publication-form').trigger('submit'); await flushPromises()
    expect(vi.mocked(catalog.updatePublication).mock.calls.map(call => [call[2].revision, call[2].title])).toEqual([[1, '新标题'], [2, '再次修改']])
    expect(catalog.catalogList).toHaveBeenCalledTimes(3)
  } finally { wrapper.unmount() }
})
it('创建后提供定位、标签与预览入口，预览后明确确认发布', async () => {
  vi.mocked(catalog.catalogSources).mockResolvedValue({ items: [{ id: 'source', title: '来源标题', grade: '三年级', subject: '数学', version: 1, file_status: 'ready', question_count: 5 }], total: 1, has_more: false })
  vi.mocked(catalog.createPublication).mockResolvedValue(paper)
  vi.mocked(catalog.catalogDetail).mockResolvedValue(paper)
  const wrapper = mountPapers()
  const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
  try {
    await flushPromises(); await button('添加习题').trigger('click'); await flushPromises()
    await wrapper.get('select[placeholder="选择习题"]').setValue('source'); await flushPromises()
    await wrapper.get('#publication-form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[aria-label="本次新建习题"]').text()).toContain('旧标题')
    expect(button('补充教学标签').exists()).toBe(true)
    await button('在列表中定位').trigger('click'); await flushPromises()
    expect(vi.mocked(catalog.catalogList).mock.lastCall?.[0]).toBe('旧标题')
    await button('预览并发布').trigger('click'); await flushPromises()
    await button('核对后设置发布').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已核对内容，确认公开发布')
    expect(button('确认发布').attributes('disabled')).toBeDefined()
    expect(catalog.updatePublication).not.toHaveBeenCalled()
  } finally { wrapper.unmount() }
})
