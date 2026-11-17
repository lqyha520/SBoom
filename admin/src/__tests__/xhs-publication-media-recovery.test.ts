import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import XhsPublicationMedia from '../components/XhsPublicationMedia.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import type { PublicationMedia } from '../xhs-media-cache'
import type { AssistMedia } from '../xhs-publish-assist'

const mocks = vi.hoisted(() => ({ read: vi.fn(), write: vi.fn(), asset: vi.fn(), blob: vi.fn() }))
vi.mock('../xhs-media-cache', () => ({ readPublicationFile: mocks.read, cachePublicationFile: mocks.write }))
vi.mock('../xhs-workspace', async original => ({ ...await original<typeof import('../xhs-workspace')>(), getAsset: mocks.asset, assetBlob: mocks.blob }))
let wrapper: VueWrapper
const local: PublicationMedia = { id: 'local', asset_id: '', name: '本机.png', media_type: 'image/png', size_bytes: 3, last_modified: 1 }
const library: PublicationMedia = { ...local, id: 'library', asset_id: 'asset-1', name: '素材.png' }
const file = (name: string) => new File(['abc'], name, { type: 'image/png', lastModified: 1 })
function start(references: PublicationMedia[]) {
  wrapper = mount(XhsPublicationMedia, { props: { owner: 7, references, modelValue: [] }, global: { stubs: { ...uiStubs, XhsAssets: true } } })
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.spyOn(URL, 'createObjectURL').mockImplementation(value => 'blob:' + (value as File).name)
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  mocks.read.mockResolvedValue(file('本机.png')); mocks.write.mockResolvedValue(undefined)
  mocks.asset.mockResolvedValue({ id: 'asset-1', data: { archived: false, rights: 'original', title: '素材.png' }, media_type: 'image/png', size_bytes: 3 })
  mocks.blob.mockResolvedValue(new Blob(['abc'], { type: 'image/png' }))
})
afterEach(() => wrapper?.unmount())

it('刷新恢复混合来源配图及顺序，不把恢复操作当作新编辑', async () => {
  start([library, local]); await flushPromises()
  expect(wrapper.findAll('img').map(image => image.attributes('src'))).toEqual(['blob:素材.png', 'blob:本机.png'])
  expect(mocks.read).toHaveBeenCalledWith(7, local)
  expect(wrapper.emitted('change')).toBeUndefined()
  expect(wrapper.emitted('availability')?.slice(-1)[0]).toEqual([true])
  await wrapper.get('button[aria-label="后移图片 1"]').trigger('click')
  expect(wrapper.emitted('change')?.slice(-1)[0]).toEqual([[local, library]])
})

it('缓存缺失保留引用并明确提示，重试能恢复原顺序', async () => {
  mocks.read.mockResolvedValueOnce(null)
  start([local, library]); await flushPromises()
  expect(wrapper.text()).toContain('以下配图暂时无法恢复：本机.png')
  expect(wrapper.emitted('change')).toBeUndefined()
  expect(wrapper.emitted('availability')?.slice(-1)[0]).toEqual([false])
  await wrapper.findAll('button').find(button => button.text() === '重试恢复配图')!.trigger('click'); await flushPromises()
  expect(wrapper.findAll('img').map(image => image.attributes('src'))).toEqual(['blob:本机.png', 'blob:素材.png'])
})

it('切换记录后丢弃上一条的慢响应，不带入旧配图', async () => {
  let finish!: (value: File) => void
  mocks.read.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  start([local]); await flushPromises()
  await wrapper.setProps({ references: [library] }); await flushPromises()
  finish(file('过期.png')); await flushPromises()
  expect(wrapper.findAll('img').map(image => image.attributes('src'))).toEqual(['blob:素材.png'])
})

it('选本机图片后写入按账号隔离的缓存，失败保留预览并提示下载', async () => {
  mocks.write.mockRejectedValue(new Error('quota'))
  start([])
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file('新图片.png')], configurable: true })
  await input.trigger('change'); await flushPromises()
  const reference = (wrapper.emitted('change')![0]![0] as PublicationMedia[])[0]!
  expect(mocks.write).toHaveBeenCalledWith(7, reference, expect.any(File), [reference.id])
  expect(wrapper.text()).toContain('本机配图暂存失败')
  expect(wrapper.findAll('img')).toHaveLength(1)
  expect((wrapper.emitted('update:modelValue')?.slice(-1)[0]?.[0] as AssistMedia[])[0]?.file.name).toBe('新图片.png')
})

it('切换管理员即使配图引用相同也重新读取，不保留上一账号文件', async () => {
  start([local]); await flushPromises()
  mocks.read.mockResolvedValueOnce(null)
  await wrapper.setProps({ owner: 8 }); await flushPromises()
  expect(mocks.read).toHaveBeenLastCalledWith(8, local)
  expect(wrapper.findAll('img')).toHaveLength(0)
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:本机.png')
  expect(wrapper.emitted('availability')?.slice(-1)[0]).toEqual([false])
})

it('父页面通过 v-model 回传配图时，保存新引用和文件而不恢复成旧列表', async () => {
  const media = ref<AssistMedia[]>([]), references = ref<PublicationMedia[]>([])
  wrapper = mount(defineComponent({ setup: () => () => h(XhsPublicationMedia, {
    owner: 7, modelValue: media.value, references: references.value,
    'onUpdate:modelValue': value => { media.value = value }, onChange: value => { references.value = value },
  }) }), { global: { stubs: { ...uiStubs, XhsAssets: true } } })
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file('一.png'), file('二.png')], configurable: true })
  await input.trigger('change'); await flushPromises()
  expect(references.value.map(item => item.name)).toEqual(['一.png', '二.png'])
  expect(media.value.map(item => item.file.name)).toEqual(['一.png', '二.png'])
  expect(mocks.write).toHaveBeenCalledTimes(2)
  expect(mocks.read).not.toHaveBeenCalled()
  await wrapper.get('button[aria-label="后移图片 1"]').trigger('click'); await flushPromises()
  expect(references.value.map(item => item.name)).toEqual(['二.png', '一.png'])
  expect(media.value.map(item => item.file.name)).toEqual(['二.png', '一.png'])
  expect(mocks.read).not.toHaveBeenCalled()
})
