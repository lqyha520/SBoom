import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { newMaterial } from '../xhs-workflow'
import XhsMaterialPreview from '../components/XhsMaterialPreview.vue'

const mocks = vi.hoisted(() => ({ pdf: vi.fn(), download: vi.fn() }))
vi.mock('../xhs-content-export', async original => ({ ...await original<typeof import('../xhs-content-export')>(), materialDocument: mocks.pdf }))
vi.mock('../../../shared/download', () => ({ downloadBlob: mocks.download }))
let wrapper: VueWrapper
type Preview = { preview: (answers?: boolean) => Promise<void>; open: boolean; loading: boolean; pages: string[] }
const data = () => ({ ...newMaterial(), title: '口算练习', questions: [{ stem: '1+1=?', options: [], answer: '2', analysis: '一加一等于二', quality_issues: [] }] })
function start() {
  wrapper = mount(XhsMaterialPreview, { props: { data: data(), session: 1 }, global: { stubs: uiStubs } })
  return wrapper.vm as unknown as Preview
}
beforeEach(() => {
  mocks.pdf.mockReset().mockImplementation(async () => ({ pdf: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), pages: ['data:image/jpeg;base64,cGFnZQ=='] })); mocks.download.mockReset()
})
afterEach(() => { wrapper?.unmount() })

it('学生卷与答案卷切换，下载与当前展示使用同一次生成的 PDF', async () => {
  const vm = start(); await vm.preview(); await flushPromises()
  expect(wrapper.get('img').attributes('alt')).toBe('学生卷第1页预览')
  await vm.preview(true); await flushPromises()
  expect(wrapper.get('img').attributes('alt')).toBe('答案讲解第1页预览')
  await wrapper.findAll('button').find(button => button.text() === '下载当前预览')!.trigger('click')
  expect(mocks.download.mock.calls[0]?.[0]).toBe((await mocks.pdf.mock.results[1]!.value).pdf)
  expect(mocks.download.mock.calls[0]?.[1]).toBe('口算练习-答案讲解.pdf')
  vm.open = false; await flushPromises()
  expect(vm.pages).toEqual([])
})

it('切换资料后旧 PDF 分页不会显示到新资料', async () => {
  let complete!: (value: { pdf: Blob; pages: string[] }) => void
  mocks.pdf.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const vm = start(), pending = vm.preview()
  await wrapper.setProps({ session: 2, data: { ...data(), title: '另一份资料' } })
  complete({ pdf: new Blob(['old PDF']), pages: ['old-page'] }); await pending; await flushPromises()
  expect(vm.pages).toEqual([])
  expect(vm.open).toBe(false)
  expect(vm.loading).toBe(false)
})

it('编辑资料后清除预览并提示重做，生成输入保留原内容快照', async () => {
  const vm = start(); await vm.preview(); await flushPromises()
  await wrapper.setProps({ data: { ...data(), instructions: '修改后的说明' } })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('资料已修改，请重新预览当前内容。')
  expect(mocks.pdf.mock.calls[0]?.[0].instructions).toBe('')
  expect(vm.pages).toEqual([])
})

it('PDF 失败展示具体原因，不留下加载状态或旧分页', async () => {
  mocks.pdf.mockRejectedValueOnce(new Error('第 1 题的答案未补全'))
  const vm = start(); await vm.preview(true); await flushPromises()
  expect(wrapper.text()).toContain('第 1 题的答案未补全')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(vm.loading).toBe(false)
})
