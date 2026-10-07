import { expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import EditionDialog from '../components/PaperEditionDialog.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import * as catalog from '../catalog'
import * as growth from '../growth'
vi.mock('../catalog', () => ({ catalogDetail: vi.fn(), attachImportedEdition: vi.fn() }))
vi.mock('../growth', () => ({ editionSources: vi.fn(), saveEdition: vi.fn() }))
vi.mock('../catalog-import-queue', () => ({ inspectPdf: vi.fn().mockResolvedValue('digest') }))

it('upload then save again keeps the newly associated edition even outside search results', async () => {
  const edition = { kind: 'answers' as const, paper_id: 'uploaded', label: '答案版', mode: 'answersOnly', byte_size: 40 }
  vi.mocked(catalog.catalogDetail).mockResolvedValue({ id: 'paper', revision: 1, editions: [], status: 'draft' } as any)
  vi.mocked(growth.editionSources).mockResolvedValue({ items: [], loose: true })
  vi.mocked(catalog.attachImportedEdition).mockResolvedValue({ revision: 2, editions: [edition] })
  vi.mocked(growth.saveEdition).mockResolvedValue({ revision: 3, editions: [edition] })
  const wrapper = mount(EditionDialog, { props: { open: false, target: { id: 'paper', title: '试卷' } as any, adminId: 1 },
    global: { stubs: uiStubs } })
  await wrapper.setProps({ open: true }); await flushPromises()
  await wrapper.get('[aria-label="文件来源"]').setValue('upload')
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['%PDF-test'], 'answers.pdf')] })
  await input.trigger('change'); await flushPromises()
  const save = () => wrapper.findAll('button').find(button => button.text() === '保存打印版本')!
  await save().trigger('click'); await flushPromises()
  expect(catalog.attachImportedEdition).toHaveBeenCalledOnce()
  expect((wrapper.get('[aria-label="关联打印文件"]').element as HTMLSelectElement).value).toBe('uploaded')
  await save().trigger('click'); await flushPromises()
  expect(growth.saveEdition).toHaveBeenCalledWith(1, 'paper', expect.objectContaining({ revision: 2, paper_id: 'uploaded' }))
  wrapper.unmount()
})
