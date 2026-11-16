import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useXhsAssetUploads } from '../xhs-asset-uploads'
const mocks = vi.hoisted(() => ({ upload: vi.fn() }))
vi.mock('../xhs-workspace', () => ({ uploadAsset: mocks.upload }))
let wrapper: ReturnType<typeof mount>, batch: ReturnType<typeof useXhsAssetUploads>
const file = (name: string) => new File(['image-data'], name, { type: 'image/png' })
beforeEach(() => { vi.resetAllMocks(); wrapper = mount(defineComponent({ setup() { batch = useXhsAssetUploads(async () => {}); return () => h('div') } })) })
afterEach(() => wrapper.unmount())
it('部分失败继续下一文件；重试只上传失败项，重复文件保留原记录', async () => {
  mocks.upload.mockResolvedValueOnce({ id: 'one', duplicate: true }).mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ id: 'three' })
  await batch.choose([file('one.png'), file('two.png'), file('three.png')])
  expect(batch.rows.value.map(row => row.status)).toEqual(['duplicate', 'failed', 'done'])
  mocks.upload.mockResolvedValueOnce({ id: 'two' }); await batch.run(true)
  expect(mocks.upload).toHaveBeenCalledTimes(4); expect(mocks.upload.mock.calls[3]![0].name).toBe('two.png')
})
it('停止等待当前文件完成，随后未开始文件保持待上传', async () => {
  let complete!: (value: unknown) => void
  mocks.upload.mockImplementation(() => new Promise(resolve => { complete = resolve }))
  const run = batch.choose([file('one.png'), file('two.png')]); batch.stop(); complete({ id: 'one' }); await run
  expect(batch.rows.value.map(row => row.status)).toEqual(['done', 'pending']); expect(mocks.upload).toHaveBeenCalledTimes(1)
})
it('超出整批数量或无效文件不发起上传', async () => {
  await batch.choose(Array.from({ length: 21 }, (_, index) => file(`${index}.png`))); expect(batch.error.value).toContain('20 个文件')
  await batch.choose([new File(['x'], 'unknown.exe', { type: 'application/octet-stream' })]); expect(batch.rows.value[0]!.status).toBe('failed')
  expect(mocks.upload).not.toHaveBeenCalled()
})
